"""Exercise the real Flask routes, not a mocked calculation service."""

import unittest
from dataclasses import replace
from unittest.mock import patch

from app import build_calculation, create_app, parse_inputs
from dc_bias import calculate_bias
from spice_engine import FIELD_SPECS, SpiceError


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

    def test_tiny_nonzero_currents_are_not_formatted_as_zero(self):
        # Same active Divider proportions with resistances scaled by 1e6.
        # The SI currents are nonzero even though 3 fixed decimals show zero.
        payload = dict(
            DEFAULT, r1="100000000", r2="22000000", re="1000000",
        )
        api = self.client.post("/api/calculate", json=payload)
        html = self.client.post("/calculate", data=payload)
        self.assertEqual(api.status_code, 200)
        self.assertEqual(html.status_code, 200)
        point = api.get_json()
        self.assertEqual(point["region"], "forward_active")
        for key, unit in (("IB_A", "µA"), ("IC_A", "mA"), ("IE_A", "mA")):
            with self.subTest(key=key):
                self.assertGreater(point["results"][key], 0.0)
                rendered_number, rendered_unit = point["display"][key].split()
                self.assertEqual(rendered_unit, unit)
                self.assertGreater(float(rendered_number), 0.0)
                self.assertIn(point["display"][key], html.get_data(as_text=True))

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


class Lab03RouteTests(unittest.TestCase):
    def setUp(self):
        application = create_app()
        application.config["TESTING"] = True
        self.client = application.test_client()
        self.common = {"vcc":"12", "rc":"2.2", "beta":"100", "vbe":"0.70"}

    def test_explicit_modes_show_independent_reference_and_preserve_legacy_wire_keys(self):
        cases = [
            ("divider", {"r1":"100","r2":"22","re":"1"}, 0.00122985814626, 8.0521553505),
            ("fixed", {"rb":"1000"}, 0.00113, 9.514),
            ("emitter", {"rb":"1000","re":"1"}, 0.00102633969119, 8.70544959128),
            ("emitter", {"rb":"1000","re":"2"}, 0.000940099833611, 8.03277870216),
        ]
        for mode, resistors, expected_ic, expected_vce in cases:
            with self.subTest(mode=mode, inputs=resistors):
                response = self.client.post("/api/calculate", json=dict(self.common, mode=mode, **resistors))
                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertEqual(data.get("mode"), mode)
                self.assertAlmostEqual(data["results"]["IC_A"], expected_ic, delta=1e-12)
                self.assertAlmostEqual(data["results"]["VCE_V"], expected_vce, delta=1e-10)
                steps = {item["id"] for item in data["calculation"]["steps"]}
                self.assertTrue({"base_kvl","collector_kvl","transistor_kcl","active_region","vbe_identity"} <= steps)
                comparison = {item["key"]:item for item in data["calculation"]["comparison"]}
                self.assertEqual(comparison["IC_A"]["state"], "match")
                self.assertAlmostEqual(comparison["IC_A"]["manual_raw"], expected_ic, delta=1e-12)
                self.assertEqual({"VTH_V","RTH_OHM"} <= comparison.keys(), mode == "divider")
        legacy = self.client.post("/api/calculate",json=DEFAULT).get_json()
        self.assertEqual(set(legacy),{"ok","region","model","results","display","checks","warnings"})

    def test_get_select_and_native_post_work_without_any_program_script(self):
        html = self.client.get("/?mode=fixed").get_data(as_text=True)
        self.assertTrue('name="rb"' in html, "Fixed mode must render the Base resistor field")
        self.assertNotIn('name="re"',html)
        self.assertNotIn('name="r1"',html)
        self.assertNotIn("1.130 mA",html)
        response = self.client.post("/calculate",data=dict(self.common,mode="fixed",rb="1000"))
        self.assertEqual(response.status_code,200)
        html = response.get_data(as_text=True)
        self.assertIn('data-result-key="IC_A">1.130 mA</',html)
        self.assertIn('id="manual-details"',html)
        self.assertIn('id="reference-schematic"',html)
        self.assertIn("V_CC = I_B × R_B + V_BE",html)

    def test_only_required_fields_apply_and_invalid_modes_do_not_fall_through(self):
        response = self.client.post("/api/calculate", json=dict(self.common,mode="fixed",rb="1000",re="bad",r1="bad"))
        self.assertEqual(response.status_code,200)
        for mode in ("","FIXED","unknown",None):
            response = self.client.post("/api/calculate",json=dict(DEFAULT,mode=mode))
            self.assertEqual(response.status_code,422)
            self.assertIn("mode",response.get_json()["errors"])
        self.assertEqual(self.client.get("/?mode=fixed&mode=divider").status_code,422)

    def test_zero_rb_and_valid_values_outside_active_are_distinct_states(self):
        response = self.client.post("/api/calculate",json=dict(self.common,mode="fixed",rb="0"))
        self.assertEqual(response.status_code,422)
        self.assertIn("rb",response.get_json()["errors"])
        response = self.client.post("/api/calculate",json=dict(self.common,mode="fixed",rb="215"))
        self.assertEqual(response.status_code,200)
        data = response.get_json()
        self.assertEqual(data["region"],"outside_model")
        self.assertIsNone(data["results"]["IC_A"])
        self.assertEqual(data["calculation"]["state"],"unavailable")
        states = {item["key"]: item["state"] for item in data["verification"]}
        self.assertEqual(states.pop("region_consistency"), "fail")
        self.assertEqual(set(states.values()), {"na"})

    def test_explicit_mode_resistance_errors_use_form_units(self):
        fields = dict(self.common, mode="fixed", rb="0")
        api = self.client.post("/api/calculate", json=fields)
        self.assertEqual(api.status_code, 422)
        self.assertIn("0.001", api.get_json()["errors"]["rb"])
        self.assertIn("kΩ", api.get_json()["errors"]["rb"])
        form = self.client.post("/calculate", data=fields)
        self.assertEqual(form.status_code, 422)
        self.assertRegex(form.get_data(as_text=True), r'data-error-key="rb">[^<]+kΩ')

    def test_exact_reference_keeps_precision_on_extreme_divider_is_separate_from_region(self):
        response = self.client.post("/api/calculate",json=dict(
            DEFAULT, mode="divider",rc="0.001",r1="0.001",r2="1e9",re="1e9"))
        self.assertEqual(response.status_code,200)
        data = response.get_json()
        self.assertEqual(data["region"],"forward_active")
        self.assertIn("calculation",data)
        ic = {row["key"]:row for row in data["calculation"]["comparison"]}["IC_A"]
        self.assertAlmostEqual(ic["manual_raw"],1.11881188119e-11,delta=1e-22)
        self.assertEqual(ic["state"],"match")
        self.assertEqual(data["calculation"]["state"],"match")

    def test_circuit_uses_compact_annotation_but_form_keeps_full_resistance(self):
        response = self.client.post("/calculate", data=dict(DEFAULT, mode="divider", r2="1000000000"))
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('name="r2" value="1000000000"', html)
        self.assertIn('data-input-key="r2">1e+09</tspan>', html)

    def test_explicit_calculation_exposes_validated_form_units_without_reparsing_raw_tokens(self):
        payload = dict(self.common, mode="fixed", vcc="1_2", rb="1_000")
        response = self.client.post("/api/calculate", json=payload)
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual(result["inputs"]["vcc"], "1_2")
        self.assertEqual(result["inputs"]["rb"], "1_000")
        self.assertEqual(result["input_values"], {"vcc":12.0,"rc":2.2,"beta":100.0,"vbe":0.7,"rb":1000.0})
        self.assertEqual(result["schematic_inputs"]["vcc"], "12")
        self.assertEqual(result["schematic_inputs"]["rb"], "1000")
        form = self.client.post("/calculate", data=payload).get_data(as_text=True)
        self.assertIn('name="vcc" value="1_2"', form)
        self.assertIn('data-input-key="vcc">12</tspan>', form)
        invalid = self.client.post("/api/calculate", json=dict(payload, rb="0"))
        self.assertEqual(invalid.status_code, 422)
        self.assertNotIn("input_values", invalid.get_json())

    def test_existing_divider_estimates_keep_their_own_calculation_branch(self):
        for payload, region, expected_step in [
            (dict(DEFAULT,vcc="5",r2="1"),"cutoff_estimate","cutoff_condition"),
            (dict(DEFAULT,vcc="5",r1="10",r2="10",rc="10"),"saturation_estimate","saturation_constraint"),
        ]:
            data = self.client.post("/api/calculate",json=dict(payload,mode="divider")).get_json()
            self.assertEqual(data["region"],region)
            self.assertIn("calculation",data)
            self.assertIn(expected_step,{step["id"] for step in data["calculation"]["steps"]})
            self.assertTrue(data["warnings"])

    def test_comparison_reports_unrounded_difference_without_changing_region(self):
        params = parse_inputs(DEFAULT)
        point = calculate_bias(params)
        modified = replace(point, values=dict(point.values, IC_A=point.values["IC_A"] + 2e-7))
        calculation = build_calculation(params, modified)
        ic = next(row for row in calculation["comparison"] if row["key"] == "IC_A")
        self.assertEqual(ic["manual"], ic["actual"])
        self.assertEqual(ic["state"], "different")
        self.assertEqual(calculation["state"], "different")
        self.assertEqual(modified.region, "forward_active")


class WorkbenchExperimentTests(unittest.TestCase):
    def setUp(self):
        application = create_app()
        application.config["TESTING"] = True
        self.client = application.test_client()
        self.emitter = {"vcc":"12", "rc":"2.2", "beta":"100", "vbe":"0.70", "rb":"1000", "re":"1"}

    def test_diagnostics_show_only_failed_trial_without_publishing_q_point(self):
        response = self.client.post("/api/calculate", json=dict(self.emitter, mode="fixed", rb="215"))
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual(result["region"], "outside_model")
        self.assertIsNone(result["results"]["VC_V"])
        self.assertEqual(result["drops"], {})
        (diagnostic,) = result["diagnostics"]
        self.assertEqual(diagnostic, {"key":"vcb", "lhs":diagnostic["lhs"], "operator":">", "rhs":0.0, "unit":"V", "pass":False})
        self.assertAlmostEqual(diagnostic["lhs"], -0.262790697674, delta=1e-12)

    def test_underflow_has_no_q_point_or_fabricated_failed_physics_predicate(self):
        cases = {"divider":DEFAULT, "fixed":self.emitter, "emitter":self.emitter}
        for mode, inputs in cases.items():
            with self.subTest(mode=mode):
                response = self.client.post("/api/calculate", json=dict(inputs, mode=mode, beta="5e-324"))
                data = response.get_json()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(data["region"], "outside_model")
                self.assertIsNone(data["results"]["IC_A"])
                self.assertEqual(data["diagnostics"], [])
                self.assertTrue(any("underflow" in warning for warning in data["warnings"]))

    def test_drops_are_from_the_solved_nodes_in_every_topology(self):
        cases = {
            "fixed": (self.emitter, {"RB":11.3,"RC":2.486}),
            "emitter": (self.emitter, {"RB":10.263396911898,"RC":2.257947320618,"RE":1.036603088102}),
            "divider": (DEFAULT, {"R1":10.057843271973,"R2":1.942156728027,"RC":2.705687921774,
                                  "RE":1.242156728027,"RTH":0.221777698203}),
        }
        for mode, (payload, expected) in cases.items():
            with self.subTest(mode=mode):
                data = self.client.post("/api/calculate", json=dict(payload, mode=mode)).get_json()
                self.assertEqual(data["diagnostics"], [])
                self.assertEqual(set(data["drops"]), set(expected))
                for key, value in expected.items():
                    self.assertAlmostEqual(data["drops"][key], value, delta=1e-9)

    def test_drops_preserve_sub_ulp_values_at_extreme_resistance_ratios(self):
        extreme = dict(DEFAULT, mode="divider", rc="0.001", r1="0.001", r2="1e9", re="1e9")
        for beta, key, reference in (("1e-6", "RC", 1.129998870000e-17), ("1e6", "RTH", 1.129998870000e-17)):
            with self.subTest(beta=beta, resistor=key):
                data = self.client.post("/api/calculate", json=dict(extreme, beta=beta)).get_json()
                self.assertEqual(data["region"], "forward_active")
                self.assertEqual(data["calculation"]["state"], "match")
                self.assertAlmostEqual(data["drops"][key], reference, delta=1e-27)

    def test_sweep_returns_every_sample_in_order_and_preserves_unavailable_gap(self):
        response = self.client.post("/api/sweep", json={
            "mode":"divider", "inputs":DEFAULT, "parameter":"rc", "start":5, "end":12,
        })
        self.assertEqual(response.status_code, 200)
        points = response.get_json()["points"]
        self.assertEqual(len(points), 41)
        self.assertEqual([p["value"] for p in points], [5 + 7 * (index/40) for index in range(41)])
        self.assertEqual(points[0]["region"], "forward_active")
        self.assertEqual(points[-1]["region"], "saturation_estimate")
        self.assertEqual({tuple(p["results"]) for p in points if p["region"] == "outside_model"}, {()})
        self.assertAlmostEqual(points[0]["results"]["IC_A"], 0.00122985814626, delta=1e-12)
        self.assertEqual(points[-1]["results"]["VCE_V"], 0.2)

    def test_sweep_rejects_invalid_fixed_fields_and_marks_out_of_bound_samples(self):
        payload = {"mode":"fixed", "inputs":self.emitter, "parameter":"rb", "start":0.0005, "end":1000}
        response = self.client.post("/api/sweep", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["points"][0], {"value":0.0005,"region":"invalid","results":{}})
        for invalid, code in (({"inputs":dict(self.emitter, rc="0")},"inputs"),
                              ({"parameter":"re"},"parameter"), ({"start":True},"range"),
                              ({"end":"inf"},"range"), ({"end":0.0005},"range")):
            response = self.client.post("/api/sweep", json=dict(payload, **invalid))
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.get_json()["code"], code)

    def test_inverse_re_solves_target_and_repeats_through_main_route(self):
        payload = {"mode":"emitter", "inputs":dict(self.emitter, re=""), "target_ic_ma":1}
        response = self.client.post("/api/inverse", json=payload)
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual(result["region"], "forward_active")
        self.assertAlmostEqual(result["re_kohm"], 130/101, delta=1e-12)
        self.assertAlmostEqual(result["results"]["IC_A"], 0.001, delta=1e-13)
        repeated = self.client.post("/api/calculate", json=dict(self.emitter, mode="emitter", re=result["re_kohm"])).get_json()
        self.assertEqual(result["results"], repeated["results"])

    def test_inverse_accepts_actual_forward_current_at_each_resistance_bound(self):
        cases = [
            dict(self.emitter, vcc=176.9041386845027, rc=0.48391418580139006, beta=5.929705907550551,
                 vbe=0.9, rb=5023768.738082106, re=0.001),
            dict(self.emitter, vcc=334.8470165240097, rc=0.11265114398976514, beta=7.707601642496708,
                 vbe=0.8, rb=16052.757072957087, re=1e9),
        ]
        for inputs in cases:
            with self.subTest(resistance=inputs["re"]):
                source = self.client.post("/api/calculate", json=dict(inputs, mode="emitter")).get_json()
                target_ma = source["results"]["IC_A"] * 1000
                response = self.client.post("/api/inverse", json={
                    "mode":"emitter", "inputs":inputs, "target_ic_ma":target_ma,
                })
                self.assertEqual(response.status_code, 200, response.get_json())
                result = response.get_json()
                self.assertEqual(result["re_kohm"], inputs["re"])
                self.assertEqual(result["results"]["IC_A"], source["results"]["IC_A"])

    def test_inverse_rejects_impossible_targets_and_non_emitter_requests(self):
        payload = {"mode":"emitter", "inputs":self.emitter, "target_ic_ma":1}
        for invalid, code in (({"mode":"fixed"},"mode"), ({"target_ic_ma":0},"target"),
                              ({"target_ic_ma":None},"target"), ({"target_ic_ma":2},"range"),
                              ({"inputs":dict(self.emitter, vcc="0.5")},"drive"),
                              ({"inputs":dict(self.emitter, rc="22")},"region")):
            response = self.client.post("/api/inverse", json=dict(payload, **invalid))
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.get_json()["code"], code)
            self.assertNotIn("re_kohm", response.get_json())
            if code == "range":
                self.assertLess(response.get_json()["target_range_ma"][1], 2)

    def test_new_routes_reject_malformed_envelopes(self):
        for route in ("/api/inverse", "/api/sweep"):
            for payload in ([], {"mode":"emitter", "inputs":[]}, {"mode":"emitter"}):
                response = self.client.post(route, json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["code"], "request")


class Lab04RouteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, LAB04_SPICE_PROFILE="profile.json",
                               LAB04_NGSPICE="ngspice", LAB04_EVIDENCE_DIR=None)
        self.client = self.app.test_client()
        self.inputs = {key: field[2] for key, field in FIELD_SPECS.items()
                       if key not in {"amp", "freq"}}

    def test_initial_page_has_no_solver_result_and_lab03_is_available(self):
        page = self.client.get("/spice")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"/static/spice.js", page.data)
        self.assertIn(b'name="re"', page.data)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_route_uses_server_settings_and_forwards_checked_data(self):
        result = {"ok": True, "analysis": "dc", "run_id": "test-run", "data": {"point": {}}}
        with patch("app.simulate", return_value=result) as engine:
            response = self.client.post("/api/spice", json={"analysis": "dc", "inputs": self.inputs})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), result)
        engine.assert_called_once_with("dc", self.inputs, profile_path="profile.json",
                                       executable="ngspice", evidence_dir=None)

    def test_route_rejects_attempt_to_select_an_arbitrary_profile(self):
        response = self.client.post("/api/spice", json={
            "analysis": "dc", "inputs": self.inputs, "profile_path": "alternate.json",
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], "request")

    def test_engine_errors_return_no_success_payload(self):
        for code, status in (("profile", 503), ("engine", 503), ("timeout", 504), ("output", 502)):
            with self.subTest(code=code), patch("app.simulate", side_effect=SpiceError(code, "error")):
                response = self.client.post("/api/spice", json={"analysis": "ac", "inputs": self.inputs})
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.get_json(), {
                    "ok": False, "code": code, "message": "error", "fields": {},
                })
