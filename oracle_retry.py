"""
oracle_retry.py — Keep retrying an OCI A1.Flex instance until capacity is available.

Setup:
    pip install oci
    # Ensure ~/.oci/config is populated (https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm)

Required env vars (or edit the CONFIG block below):
    OCI_COMPARTMENT_ID   — OCID of the compartment to launch into
    OCI_SUBNET_ID        — OCID of the subnet (must be in us-ashburn-1)
    OCI_SSH_PUBLIC_KEY   — contents of your ~/.ssh/id_rsa.pub (or ed25519)
    OCI_IMAGE_ID         — (optional) pin a specific Ubuntu 22.04 ARM image OCID;
                           if omitted the script queries the latest one automatically
"""

import os
import signal
import sys
import time

import oci
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────
COMPARTMENT_ID = os.getenv("OCI_COMPARTMENT_ID", "")
SUBNET_ID      = os.getenv("OCI_SUBNET_ID", "")
SSH_PUBLIC_KEY = os.getenv("OCI_SSH_PUBLIC_KEY", "")
PINNED_IMAGE   = os.getenv("OCI_IMAGE_ID", "")       # leave blank = auto-detect

DISPLAY_NAME    = "a1-flex-auto"
SHAPE           = "VM.Standard.A1.Flex"
OCPUS           = 1
MEMORY_GB       = 6
RETRY_SECONDS   = 300   # 5 minutes between full AD cycles
REGION          = "us-ashburn-1"
# ──────────────────────────────────────────────────────────────────────────────

SEP = "─" * 60


def log(msg: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]  {msg}", flush=True)


def get_availability_domains(identity_client) -> list:
    ads = identity_client.list_availability_domains(COMPARTMENT_ID).data
    log(f"Found {len(ads)} availability domain(s): {[a.name for a in ads]}")
    return ads


def get_ubuntu_arm_image(compute_client) -> str:
    """Return the OCID of the latest Ubuntu 22.04 ARM64 platform image."""
    if PINNED_IMAGE:
        log(f"Using pinned image: {PINNED_IMAGE}")
        return PINNED_IMAGE

    log("Searching for latest Ubuntu 22.04 ARM64 image...")
    images = oci.pagination.list_call_get_all_results(
        compute_client.list_images,
        COMPARTMENT_ID,
        operating_system="Canonical Ubuntu",
        operating_system_version="22.04",
        sort_by="TIMECREATED",
        sort_order="DESC",
    ).data

    # A1 requires ARM / aarch64 images
    for img in images:
        name = (img.display_name or "").lower()
        if "aarch64" in name or "arm64" in name:
            log(f"Selected image: {img.display_name}  ({img.id})")
            return img.id

    # fallback: try the first image that lists A1 in its shape compatibility
    for img in images:
        try:
            compat = compute_client.list_image_shape_compatibility_entries(img.id).data
            if any(SHAPE in (e.shape_name or "") for e in compat):
                log(f"Selected compatible image: {img.display_name}  ({img.id})")
                return img.id
        except Exception:
            continue

    raise RuntimeError(
        "Could not find a Ubuntu 22.04 ARM64 image in this compartment. "
        "Set OCI_IMAGE_ID manually."
    )


def try_ad(compute_client, ad_name: str, image_id: str):
    """Attempt to launch in one availability domain. Returns instance or None."""
    launch_details = oci.core.models.LaunchInstanceDetails(
        availability_domain=ad_name,
        compartment_id=COMPARTMENT_ID,
        display_name=DISPLAY_NAME,
        image_id=image_id,
        shape=SHAPE,
        shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=float(OCPUS),
            memory_in_gbs=float(MEMORY_GB),
        ),
        create_vnic_details=oci.core.models.CreateVnicDetails(
            subnet_id=SUBNET_ID,
            assign_public_ip=True,
        ),
        metadata={"ssh_authorized_keys": SSH_PUBLIC_KEY},
    )
    return compute_client.launch_instance(launch_details).data


def is_capacity_error(exc: oci.exceptions.ServiceError) -> bool:
    msg = (exc.message or "").lower()
    return exc.status in (429, 500) and (
        "out of host capacity" in msg
        or "out of capacity"   in msg
        or "insufficient capacity" in msg
    )


def run_attempt(compute_client, ads: list, image_id: str, attempt: int):
    log(SEP)
    log(f"Attempt #{attempt} — trying {len(ads)} availability domain(s)")
    for ad in ads:
        log(f"  → {ad.name} ...")
        try:
            instance = try_ad(compute_client, ad.name, image_id)
            return instance
        except oci.exceptions.ServiceError as exc:
            if is_capacity_error(exc):
                log(f"     No capacity  (HTTP {exc.status})")
            else:
                log(f"     API error: [{exc.status}] {exc.code} — {exc.message}")
        except Exception as exc:
            log(f"     Unexpected error: {exc}")
    return None


def validate_config() -> None:
    missing = [k for k, v in [
        ("OCI_COMPARTMENT_ID", COMPARTMENT_ID),
        ("OCI_SUBNET_ID",      SUBNET_ID),
        ("OCI_SSH_PUBLIC_KEY", SSH_PUBLIC_KEY),
    ] if not v]
    if missing:
        print("ERROR: Missing required configuration:")
        for m in missing:
            print(f"  export {m}=...")
        sys.exit(1)


def main() -> None:
    validate_config()

    # graceful Ctrl+C
    signal.signal(signal.SIGINT, lambda *_: (print("\nAborted."), sys.exit(0)))

    cfg = oci.config.from_file()
    cfg["region"] = REGION

    compute_client  = oci.core.ComputeClient(cfg)
    identity_client = oci.identity.IdentityClient(cfg)

    log(f"Starting A1.Flex retry loop — region={REGION}  shape={SHAPE}")
    log(f"Target: {OCPUS} OCPU / {MEMORY_GB} GB RAM  |  retry every {RETRY_SECONDS}s")
    log(SEP)

    ads      = get_availability_domains(identity_client)
    image_id = get_ubuntu_arm_image(compute_client)
    attempt  = 0

    while True:
        attempt += 1
        instance = run_attempt(compute_client, ads, image_id, attempt)

        if instance:
            log(SEP)
            log("SUCCESS — instance launched!")
            log(SEP)
            print(f"  Instance ID   : {instance.id}")
            print(f"  Display name  : {instance.display_name}")
            print(f"  State         : {instance.lifecycle_state}")
            print(f"  AD            : {instance.availability_domain}")
            print(f"  Shape         : {instance.shape}")
            print(f"  Region        : {REGION}")
            print()
            print("The instance is provisioning. Check the OCI console or run:")
            print(f"  oci compute instance get --instance-id {instance.id}")
            break

        log(f"All ADs exhausted on attempt #{attempt}. "
            f"Waiting {RETRY_SECONDS // 60}m before next cycle...")
        time.sleep(RETRY_SECONDS)


if __name__ == "__main__":
    main()
