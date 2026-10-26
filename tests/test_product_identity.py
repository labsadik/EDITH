"""Identity configuration and prompt fallback are independent of provider imports."""
import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
import unittest

from core.product_identity import PRODUCT_IDENTITY


class ProductIdentityTests(unittest.TestCase):
    def test_product_metadata_is_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            PRODUCT_IDENTITY.name = 'external override'
        self.assertEqual(PRODUCT_IDENTITY.assistant, 'EDITH')
        self.assertEqual(PRODUCT_IDENTITY.short_name, 'NL')
        self.assertEqual(PRODUCT_IDENTITY.built_by, 'Sadik Laskar')

    def load_prompt(self, read):
        source = Path(__file__).resolve().parents[1] / 'main.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == '_load_system_prompt')
        module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
        namespace = {'PROMPT_PATH': SimpleNamespace(read_text=read),
                     'PRODUCT_IDENTITY': PRODUCT_IDENTITY}
        exec(compile(module, str(source), 'exec'), namespace)
        return namespace['_load_system_prompt']()

    def test_runtime_prompt_ends_with_code_owned_identity(self):
        prompt = self.load_prompt(lambda **kwargs: 'Main instructions')
        self.assertTrue(prompt.startswith('Main instructions'))
        self.assertTrue(prompt.endswith(PRODUCT_IDENTITY.instruction()))

    def test_unreadable_prompt_still_includes_identity_and_action_checks(self):
        def fail(**kwargs):
            raise OSError('unavailable')
        prompt = self.load_prompt(fail)
        self.assertIn('Never simulate actions', prompt)
        self.assertIn('Neuron Intelligence', prompt)
        self.assertIn('Sadik Laskar', prompt)
