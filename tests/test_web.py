"""Exercise the real Flask routes, not a mocked calculation service."""

import unittest

from app import create_app


DEFAULT = {
    "vcc": "12", "r1": "100", "r2": "22", "rc": "2.2",
    "re": "1", "beta": "100", "vbe": "0.70",
}


class FlaskRouteTests(unittest.TestCase):
    def setUp(self):
        app = create_app()
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_get_root_renders_real_default_result(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        for key in DEFAULT:
            self.assertIn(f'name="{key}"', html)
        self.assertIn("1.942 V", html)
        self.assertIn("1.230 mA", html)

    def test_post_form_recalculates_when_resistance_changes(self):
        response = self.client.post("/calculate", data=dict(DEFAULT, rc="3.3"))
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("7.941 V", html)
        self.assertNotIn("9.294 V", html)

    def test_json_endpoint_returns_independent_reference_value(self):
        response = self.client.post("/api/calculate", json=DEFAULT)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["region"], "forward_active")
        self.assertAlmostEqual(data["results"]["IC_A"], 0.001229858146, delta=1e-10)
        self.assertEqual(data["display"]["IC_A"], "1.230 mA")

    def test_invalid_input_shows_inline_error_and_api_4xx(self):
        for field, value in (
            ("r1", "0"), ("r2", "-1"), ("vcc", ""),
            ("beta", "abc"), ("vbe", "NaN"), ("rc", "Infinity"),
        ):
            with self.subTest(field=field, value=value):
                payload = dict(DEFAULT, **{field: value})
                form = self.client.post("/calculate", data=payload)
                self.assertEqual(form.status_code, 422)
                self.assertIn("Input error", form.get_data(as_text=True))
                api = self.client.post("/api/calculate", json=payload)
                self.assertEqual(api.status_code, 422)
                self.assertFalse(api.get_json()["ok"])
                self.assertIn(field, api.get_json()["errors"])

    def test_malformed_json_payload_returns_400(self):
        bad_requests = [
            self.client.post("/api/calculate", data="{", content_type="application/json"),
            self.client.post("/api/calculate", json=[1, 2]),
            self.client.post("/api/calculate", data="not json", content_type="text/plain"),
        ]
        for response in bad_requests:
            self.assertEqual(response.status_code, 400)
            self.assertFalse(response.get_json()["ok"])

    def test_schematic_and_cards_share_backend_data_bindings(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("<svg", html)
        self.assertIn('viewBox="', html)
        self.assertIn('role="img"', html)
        self.assertIn("<title", html)
        self.assertIn("<desc", html)
        for key in ("VB_V", "VE_V", "VC_V", "VCE_V", "IB_A", "IC_A", "IE_A"):
            with self.subTest(key=key):
                self.assertGreaterEqual(html.count(f'data-result-key="{key}"'), 2)

    def test_schematic_uses_no_external_script_or_raster_diagram(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("static/app.js", html)
        self.assertNotIn("<script src=", html)
        self.assertNotIn("<img", html)
        self.assertIn("bias-form", html)

    def test_english_interface_declares_matching_document_language(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('<html lang="en">', html)

    def test_html_and_json_share_all_backend_display_values(self):
        payload = dict(DEFAULT, rc="3.3")
        html_response = self.client.post("/calculate", data=payload)
        api_response = self.client.post("/api/calculate", json=payload)
        self.assertEqual(html_response.status_code, 200)
        self.assertEqual(api_response.status_code, 200)
        html = html_response.get_data(as_text=True)
        calculated = api_response.get_json()
        self.assertTrue(all(calculated["checks"].values()))
        for key, displayed in calculated["display"].items():
            with self.subTest(key=key):
                self.assertIn(f'data-result-key="{key}">{displayed}</', html)
        self.assertNotIn("9.294 V", html)

    def test_cutoff_and_saturation_warnings_present_in_both_modes(self):
        cases = [
            (dict(DEFAULT, vcc="5", r1="100", r2="1"), "cutoff_estimate"),
            (dict(DEFAULT, vcc="5", r1="10", r2="10", rc="10"), "saturation_estimate"),
        ]
        for payload, region in cases:
            with self.subTest(region=region):
                html_response = self.client.post("/calculate", data=payload)
                api_response = self.client.post("/api/calculate", json=payload)
                self.assertEqual(html_response.status_code, 200)
                self.assertEqual(api_response.status_code, 200)
                data = api_response.get_json()
                html = html_response.get_data(as_text=True)
                self.assertEqual(data["region"], region)
                self.assertTrue(data["warnings"])
                self.assertTrue(all(data["checks"].values()))
                self.assertIn(f'data-region="{region}"', html)
                for warning in data["warnings"]:
                    self.assertIn(warning, html)

    def test_outside_model_does_not_publish_false_q_point(self):
        # A saturated VCE=0.20 V cannot coexist with VBE=0.10 V
        # and a forward-biased base-collector junction.
        payload = dict(DEFAULT, vcc="5", r1="10", r2="10", rc="10", vbe="0.10")
        api = self.client.post("/api/calculate", json=payload)
        html = self.client.post("/calculate", data=payload).get_data(as_text=True)
        self.assertEqual(api.status_code, 200)
        data = api.get_json()
        self.assertEqual(data["region"], "outside_model")
        self.assertEqual(data["display"]["VB_V"], "—")
        self.assertIsNone(data["results"]["IC_A"])
        self.assertFalse(data["checks"]["region_consistency"])
        self.assertIn('data-region="outside_model"', html)
        self.assertIn('data-result-key="VB_V">—</', html)

    def test_reset_returns_to_defaults_without_javascript(self):
        html = self.client.post(
            "/calculate", data=dict(DEFAULT, rc="3.3")
        ).get_data(as_text=True)
        # HTML reset must navigate to server defaults, not merely reset the
        # just-submitted form's current value when scripts are disabled.
        self.assertRegex(html, r'<a[^>]*id="reset-button"[^>]*href="/"')
