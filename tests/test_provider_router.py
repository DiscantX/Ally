import unittest
from unittest.mock import MagicMock
from infrastructure.llm.provider_router import ProviderRouter

class TestProviderRouter(unittest.TestCase):
    def test_call_with_fallback_success_first(self):
        prov1 = MagicMock()
        prov1.generate_structured.return_value = "success-1"
        prov2 = MagicMock()
        prov2.generate_structured.return_value = "success-2"

        router = ProviderRouter([prov1, prov2])
        res = router.call_with_fallback("generate_structured", model="m", contents=["p"], schema=MagicMock())
        self.assertEqual(res, "success-1")
        prov1.generate_structured.assert_called_once()
        prov2.generate_structured.assert_not_called()

    def test_call_with_fallback_triggers_fallback(self):
        prov1 = MagicMock()
        prov1.generate_structured.side_effect = RuntimeError("API down")
        prov2 = MagicMock()
        prov2.generate_structured.return_value = "success-fallback"

        router = ProviderRouter([prov1, prov2])
        res = router.call_with_fallback("generate_structured", model="m", contents=["p"], schema=MagicMock())
        self.assertEqual(res, "success-fallback")
        prov1.generate_structured.assert_called_once()
        prov2.generate_structured.assert_called_once()

    def test_call_with_fallback_all_fail(self):
        prov1 = MagicMock()
        prov1.generate_structured.side_effect = RuntimeError("err1")
        prov2 = MagicMock()
        prov2.generate_structured.side_effect = RuntimeError("err2")

        router = ProviderRouter([prov1, prov2])
        with self.assertRaises(RuntimeError):
            router.call_with_fallback("generate_structured", model="m", contents=["p"], schema=MagicMock())

    def test_call_concurrent(self):
        prov1 = MagicMock()
        prov1.generate_structured.return_value = "res-1"
        prov2 = MagicMock()
        prov2.generate_structured.return_value = "res-2"

        router = ProviderRouter([prov1, prov2])
        results = router.call_concurrent("generate_structured", model="m", contents=["p"], schema=MagicMock())
        self.assertEqual(results, {0: "res-1", 1: "res-2"})
