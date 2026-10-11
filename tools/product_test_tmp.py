"""Local Windows pytest temp fixture workaround, without deselecting tests.

Use with -p no:tmpdir -p tools.product_test_tmp. The normal tmpdir plugin
changes directory ACLs on this host and fails with WinError 5. Plain mkdir
works. All test directories remain separate and inspectable until removed.
"""
from pathlib import Path
import uuid

import pytest


class ProductTempFactory:
    def __init__(self):
        self.root = Path(__file__).resolve().parents[1] / ".product-test-tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)

    def getbasetemp(self):
        return self.root

    def mktemp(self, basename, numbered=True):
        path = self.root / (basename + "-" + uuid.uuid4().hex)
        path.mkdir()
        return path


@pytest.fixture(scope="session")
def tmp_path_factory():
    return ProductTempFactory()


@pytest.fixture
def tmp_path(tmp_path_factory, request):
    return tmp_path_factory.mktemp(request.node.name[:60].replace("/", "_"))
