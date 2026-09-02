import unittest

import numpy as np
import cv2

from beem_agent.geometry import detect_screen_and_projection, insets_to_source_quad, solve_insets, source_quad_to_insets


class GeometryTests(unittest.TestCase):
    def test_inset_round_trip(self):
        insets = {"lt": [20, 30], "rt": [40, 50], "rb": [60, 70], "lb": [80, 90]}
        self.assertEqual(source_quad_to_insets(insets_to_source_quad(insets)), insets)

    def test_identity_photo_keeps_zero_insets(self):
        quad = [[100, 100], [900, 100], [900, 600], [100, 600]]
        zero = {corner: [0, 0] for corner in ("lt", "rt", "rb", "lb")}
        self.assertEqual(solve_insets(quad, quad, zero), zero)

    def test_target_inside_projection_becomes_insets(self):
        projection = [[0, 0], [1000, 0], [1000, 500], [0, 500]]
        screen = [[100, 50], [900, 50], [900, 450], [100, 450]]
        zero = {corner: [0, 0] for corner in ("lt", "rt", "rb", "lb")}
        expected = {corner: [50, 50] for corner in ("lt", "rt", "rb", "lb")}
        self.assertEqual(solve_insets(projection, screen, zero), expected)

    def test_small_detection_overshoot_is_clamped_but_large_miss_is_rejected(self):
        slightly_outside = np.array([[-0.02, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]])
        self.assertEqual(source_quad_to_insets(slightly_outside)["lt"], [0, 50])
        too_far = slightly_outside.copy()
        too_far[0, 0] = -0.03
        with self.assertRaisesRegex(ValueError, "outside"):
            source_quad_to_insets(too_far)

    def test_detects_projection_instead_of_duplicate_frame_edge(self):
        image = np.full((900, 1400, 3), 20, np.uint8)
        screen = np.array([[160, 100], [1240, 140], [1180, 800], [200, 760]], np.int32)
        projection = np.array([[250, 190], [1140, 210], [1080, 700], [280, 690]], np.int32)
        cv2.polylines(image, [screen], True, (210, 210, 210), 14)
        cv2.fillConvexPoly(image, projection, (245, 245, 245))

        detected = detect_screen_and_projection(image)

        self.assertLess(np.abs(detected.screen - screen).mean(), 12)
        self.assertLess(np.abs(detected.projection - projection).mean(), 12)


if __name__ == "__main__":
    unittest.main()
