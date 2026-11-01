# plane-unlimited: fix Plane's S3Storage for django-storages' save() path.
#
# Plane's S3Storage.__init__ never calls S3Boto3Storage.__init__, so attributes
# like `location` are missing and any Django FileField save through the default
# storage raises "'S3Storage' object has no attribute 'location'". The class is
# only shipped as bytecode in the commercial image, so we wrap __init__ here at
# import time instead of editing it.
import os
import sys


def _patch_s3_storage(S3Storage):
    if getattr(S3Storage, "__unlimited_patched__", False):
        return
    original_init = S3Storage.__init__

    def __init__(self, request=None):
        # Let django-storages set up its own attributes (location, bucket_name,
        # ...) from the same environment Plane reads.
        super(S3Storage, self).__init__(
            access_key=os.environ.get("AWS_ACCESS_KEY_ID"),
            secret_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            bucket_name=os.environ.get("AWS_S3_BUCKET_NAME"),
            endpoint_url=os.environ.get("AWS_S3_ENDPOINT_URL")
            or os.environ.get("MINIO_ENDPOINT_URL"),
            region_name=os.environ.get("AWS_REGION"),
        )
        original_init(self, request)

    S3Storage.__init__ = __init__
    S3Storage.__unlimited_patched__ = True


class _S3StorageFinder:
    """Import hook that patches plane.settings.storage right after it loads."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "plane.settings.storage":
            return None
        sys.meta_path.remove(self)
        try:
            spec = __import__("importlib.util", fromlist=["find_spec"]).find_spec(
                fullname, path
            )
        finally:
            pass
        if spec is None or spec.loader is None:
            return None

        inner_loader = spec.loader

        class _Loader:
            def create_module(self, spec):
                return inner_loader.create_module(spec)

            def exec_module(self, module):
                inner_loader.exec_module(module)
                try:
                    _patch_s3_storage(module.S3Storage)
                except Exception:
                    # Never break application startup over the patch.
                    pass

        spec.loader = _Loader()
        return spec


sys.meta_path.insert(0, _S3StorageFinder())
