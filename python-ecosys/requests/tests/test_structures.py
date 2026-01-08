import unittest

from requests.structures import CaseInsensitiveDict


class TestCaseInsensitiveDict(unittest.TestCase):
    def setUp(self):
        """CaseInsensitiveDict instance with "Accept" header."""
        self.case_insensitive_dict = CaseInsensitiveDict()
        self.case_insensitive_dict["Accept"] = "application/json"

    def test_list(self):
        self.assertEqual(list(self.case_insensitive_dict), ["Accept"])

    def test_getitem(self):
        possible_keys = ("accept", "ACCEPT", "aCcEpT", "Accept")
        for key in possible_keys:
            with self.subTest(key=key):
                self.assertEqual(self.case_insensitive_dict[key], "application/json")

    def test_delitem(self):
        possible_keys = ("accept", "ACCEPT", "aCcEpT", "Accept")
        for key in possible_keys:
            with self.subTest(key=key):
                # Reset the dict for each subtest
                self.case_insensitive_dict["Accept"] = "application/json"
                del self.case_insensitive_dict[key]
                self.assertNotIn(key, self.case_insensitive_dict)

    def test_lower_items(self):
        self.assertEqual(
            list(self.case_insensitive_dict.lower_items()),
            [("accept", "application/json")]
        )

    def test_repr(self):
        self.assertEqual(
            repr(self.case_insensitive_dict),
            "{'Accept': 'application/json'}"
        )

    def test_copy(self):
        copy = self.case_insensitive_dict.copy()
        self.assertIsNot(copy, self.case_insensitive_dict)
        self.assertEqual(copy, self.case_insensitive_dict)

    def test_instance_equality(self):
        test_cases = [
            ({"AccePT": "application/json"}, True),
            ({}, False),
            (None, False),
        ]
        for other, result in test_cases:
            with self.subTest(other=other, result=result):
                self.assertIs((self.case_insensitive_dict == other), result)


if __name__ == '__main__':
    unittest.main()
