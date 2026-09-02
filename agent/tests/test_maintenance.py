from __future__ import annotations

import unittest
from unittest.mock import patch

from beem_agent import server


class MaintenanceTests(unittest.TestCase):
    def test_runtime_asset_inventory_exists_and_has_safe_modes(self) -> None:
        self.assertTrue(server.RUNTIME_ASSETS)
        for relative, mode in server.RUNTIME_ASSETS.items():
            self.assertFalse(relative.startswith("/"))
            self.assertTrue((server.MODULE_SOURCE / relative).is_file(), relative)
            self.assertIn(mode, (0o644, 0o755))

    def test_deploy_requires_exact_confirmation(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicit deployment approval"):
            server.deploy_tvremoteweb_runtime("yes")

    def test_screen_timeout_accepts_android_never_value(self) -> None:
        with patch.object(server, "_shell", return_value="0") as shell, patch.object(
            server, "_getprop", return_value="0"
        ):
            server.set_projector_configuration("screen_off_timeout", 2_147_483_647, "APPLY")
        self.assertTrue(
            any(
                call.args[0] == "settings put system screen_off_timeout 2147483647"
                and call.kwargs == {"root": True, "prepare_change": True}
                for call in shell.call_args_list
            )
        )

    def test_module_prop_parser_ignores_non_properties(self) -> None:
        self.assertEqual(
            server._parse_module_prop("id=tvremoteweb\ninvalid\nversion=1.1.0\n"),
            {"id": "tvremoteweb", "version": "1.1.0"},
        )

    def test_picture_profile_requires_all_valid_channels(self) -> None:
        profile = {name: low for name, (_, low, _) in server.PICTURE_CHANNELS.items()}
        self.assertEqual(server._validate_picture_values(profile), profile)
        with self.assertRaisesRegex(ValueError, "profile mismatch"):
            server._validate_picture_values({"brightness": 50})
        profile["gamma"] = 5
        with self.assertRaisesRegex(ValueError, "gamma must be between 0 and 4"):
            server._validate_picture_values(profile)

    def test_dark_photo_proposal_is_conservative_and_complete(self) -> None:
        current = {
            "brightness": 60, "contrast": 62, "saturation": 65, "hue": 50,
            "sharpness": 50, "backlight": 100, "tnr": 2, "snr": 1,
            "dci": 2, "black_extension": 2, "dynamic_backlight": 0,
            "color_temperature": 0, "gamma": 3,
        }
        metrics = {
            "luma_p5": 3.0, "luma_p50": 60.0, "luma_p95": 145.0,
            "shadow_clip": 0.1, "highlight_clip": 0.0,
            "mean_saturation": 60.0, "laplacian_variance": 100.0,
            "mean_red": 100.0, "mean_blue": 100.0,
        }
        proposed, reasons = server._suggest_picture_settings(metrics, current)
        self.assertEqual(set(proposed), set(server.PICTURE_CHANNELS))
        self.assertEqual(proposed["brightness"], 67)
        self.assertEqual(proposed["gamma"], 2)
        self.assertEqual(proposed["black_extension"], 1)
        self.assertTrue(reasons)


if __name__ == "__main__":
    unittest.main()
