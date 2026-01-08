import unittest
from unittest.mock import patch

from requests.help import info


class VersionedPackage:
    def __init__(self, version):
        self.__version__ = version


class TestHelp(unittest.TestCase):
    def test_system_ssl(self):
        """Verify we're actually setting system_ssl when it should be available."""
        self.assertNotEqual(info()["system_ssl"]["version"], "")

    @patch("requests.help.idna", new=None)
    def test_idna_without_version_attribute(self):
        """Older versions of IDNA don't provide a __version__ attribute, verify
        that if we have such a package, we don't blow up.
        """
        self.assertEqual(info()["idna"], {"version": ""})

    @patch("requests.help.idna", new=VersionedPackage("2.6"))
    def test_idna_with_version_attribute(self):
        """Verify we're actually setting idna version when it should be available."""
        self.assertEqual(info()["idna"], {"version": "2.6"})


if __name__ == '__main__':
    unittest.main()
