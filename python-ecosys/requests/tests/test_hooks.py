import unittest

from requests import hooks


def hook(value):
    return value[1:]


class TestHooks(unittest.TestCase):
    def test_hooks(self):
        test_cases = [
            (hook, "ata"),
            ([hook, lambda x: None, hook], "ta"),
        ]
        for hooks_list, result in test_cases:
            with self.subTest(hooks_list=hooks_list, result=result):
                self.assertEqual(
                    hooks.dispatch_hook("response", {"response": hooks_list}, "Data"),
                    result
                )

    def test_default_hooks(self):
        self.assertEqual(hooks.default_hooks(), {"response": []})


if __name__ == '__main__':
    unittest.main()
