# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from mesures import bus, car, common, truck, vehicle_check  # noqa: E402
from mesures.job import guess_family, run_job  # noqa: E402
from mesures.options import JobOptions  # noqa: E402


def write(path, text):
    with open(path, "wb") as fh:
        fh.write(text.encode("latin-1"))


def read(path):
    with open(path, "rb") as fh:
        return fh.read().decode("latin-1")


def measure_file(path, values, crc=None, extra=""):
    body = "[MESURES]\r\n" + "".join("%s=%s\r\n" % kv for kv in values.items()) + extra
    body += "[CRC]\r\n" + "".join("%s=%s\r\n" % kv for kv in (crc or {}).items())
    write(path, body)


class CommonTests(unittest.TestCase):
    def test_checksum_schemes(self):
        s = "14112026150918"
        self.assertEqual(common.checksum(s, "cyclic"), sum(ord(c) * ((i % 5) + 1) for i, c in enumerate(s)))
        self.assertEqual(common.checksum(s, "linear"), sum(ord(c) * (i + 1) for i, c in enumerate(s)))
        self.assertNotEqual(common.checksum(s, "cyclic"), common.checksum(s, "linear"))
        self.assertEqual(common.checksum("1234", "cyclic"), common.checksum("1234", "linear"))

    def test_stamp(self):
        self.assertEqual(common.now_stamp(datetime(2026, 11, 14, 15, 9, 18)), "14112026150918")
        self.assertEqual(common.split_stamp("14112026150918"), ("14/11/2026", "15:09:18"))
        with self.assertRaises(common.ReportError):
            common.split_stamp("123")

    def test_scheme_detection_from_file(self):
        old = "01012026101010"
        for scheme in ("cyclic", "linear"):
            lines = ["[MESURES]", "1106=" + old, "[CRC]", "1106=%d" % common.checksum(old, scheme)]
            found, _ = common.detect_crc_scheme([lines], [("1106",)], default="cyclic" if scheme == "linear" else "linear")
            self.assertEqual(found, scheme)
        # rien a verifier -> schema par defaut
        found, _ = common.detect_crc_scheme([["[MESURES]", "1106=", "[CRC]", "1106=7"]], [("1106",)], "linear")
        self.assertEqual(found, "linear")

    def test_apply_date_crc_sections(self):
        lines = ["[A]", "0427=x", "[MESURES]", "0427=old", "[B]", "0427=other", "[CRC]", "0427=1", "[C]", "0427=z"]
        out, fm, fc = common.apply_date_crc(lines, ("0427",), "D", 9, reset_on_other=False)
        self.assertEqual(out, ["[A]", "0427=x", "[MESURES]", "0427=D", "[B]", "0427=D", "[CRC]", "0427=9", "[C]", "0427=9"])
        out, fm, fc = common.apply_date_crc(lines, ("0427",), "D", 9, reset_on_other=True)
        self.assertEqual(out, ["[A]", "0427=x", "[MESURES]", "0427=D", "[B]", "0427=other", "[CRC]", "0427=9", "[C]", "0427=z"])

    def test_formats(self):
        self.assertEqual(common.int_text({"k": "049"}, "k"), "49")
        self.assertEqual(common.int_text({"k": "x"}, "k", "-"), "-")
        self.assertEqual(common.sum_text({"a": "1", "b": "2"}, ("a", "b", "c"), "-"), "3")
        self.assertEqual(common.sum_text({}, ("a",), "-"), "-")
        self.assertEqual(common.escape_html('a&b<"c">'), "a&amp;b&lt;&quot;c&quot;&gt;")

    def test_move_conflicts(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as dest:
            write(os.path.join(d, "a.F"), "new")
            write(os.path.join(dest, "a.F"), "old")
            common.move_files([os.path.join(d, "a.F")], dest, "rename", lambda m: None)
            self.assertEqual(len(os.listdir(dest)), 2)
            self.assertEqual(os.listdir(d), [])
            write(os.path.join(d, "a.F"), "newer")
            common.move_files([os.path.join(d, "a.F")], dest, "overwrite", lambda m: None)
            self.assertEqual(read(os.path.join(dest, "a.F")), "newer")


class CarTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(car.rip({"k": "-01.6"}, "k"), "-1.6")
        self.assertEqual(car.rip({"k": "+04.1"}, "k"), "+4.1")
        self.assertEqual(car.rip({"k": "+00.0"}, "k"), "0.0")
        self.assertEqual(car.rip_comma({"k": "-01.6"}, "k"), "-1,6")
        self.assertEqual(car.dec({"k": "00,00"}, "k"), "0,00")
        self.assertEqual(car.pct(1, 8), "13")
        self.assertIsNone(car.pct(5, 0))

    def test_update_all_files_and_crlf(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "123.F")
            write(p, "[ENTETE]\n0427=keep\n[MESURES]\n0427=old\n0450=old\n0420=361\n[CRC]\n0468=1\n0427=2\n")
            n = car.update_measure_files(d, "14112026150918", lambda m: None)
            crc = common.checksum("14112026150918", "cyclic")
            self.assertEqual(read(p), "[ENTETE]\r\n0427=keep\r\n[MESURES]\r\n0427=14112026150918\r\n"
                                      "0450=14112026150918\r\n0420=361\r\n[CRC]\r\n0468=%d\r\n0427=%d\r\n" % (crc, crc))
            self.assertEqual(n, 4)

    def test_mode(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(car.detect_mode(d), car.MODE_ESSENCE)
            write(os.path.join(d, "a.O"), "[MESURES]\r\n")
            self.assertEqual(car.detect_mode(d), car.MODE_GAZOLE)
            write(os.path.join(d, "a.G"), "[MESURES]\r\n")
            self.assertEqual(car.detect_mode(d), car.MODE_ESSENCE)

    def test_run_job_car(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as dest:
            write(os.path.join(d, "tpl.html"), '<html><head></head><body><div id="pf2"></div></body></html>')
            measure_file(os.path.join(d, "5.F"), {"0427": "0"}, {"0468": "0"})
            opt = JobOptions(folder=d, dest=dest, make_pdf=False, do_print=False, tpl_essence="tpl.html", app_dir=d,
                             check_cg=False, delete_report=False)
            self.assertTrue(run_job(opt, lambda m: None))
            self.assertTrue(os.path.isfile(os.path.join(d, "rapport_a_imprimer.html")))   # conserve
            self.assertTrue(os.path.isfile(os.path.join(dest, "5.F")))

    def test_report_deleted_after_move_by_default(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as dest:
            write(os.path.join(d, "tpl.html"), '<html><head></head><body><div id="pf2"></div></body></html>')
            write(os.path.join(d, "rapport_a_imprimer.pdf"), "old pdf")
            measure_file(os.path.join(d, "5.F"), {"0427": "0"}, {"0468": "0"})
            opt = JobOptions(folder=d, dest=dest, make_pdf=False, do_print=False, tpl_essence="tpl.html",
                             app_dir=d, check_cg=False)
            self.assertTrue(run_job(opt, lambda m: None))
            self.assertFalse(os.path.exists(os.path.join(d, "rapport_a_imprimer.html")))
            self.assertFalse(os.path.exists(os.path.join(d, "rapport_a_imprimer.pdf")))
            self.assertTrue(os.path.isfile(os.path.join(dest, "5.F")))

    def test_report_kept_when_files_not_moved(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "tpl.html"), '<html><head></head><body><div id="pf2"></div></body></html>')
            measure_file(os.path.join(d, "5.F"), {"0427": "0"}, {"0468": "0"})
            opt = JobOptions(folder=d, move_files=False, make_pdf=False, do_print=False,
                             tpl_essence="tpl.html", app_dir=d, check_cg=False)
            self.assertTrue(run_job(opt, lambda m: None))
            self.assertTrue(os.path.isfile(os.path.join(d, "rapport_a_imprimer.html")))

    def test_car_without_measure_files_stops(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as dest:
            write(os.path.join(d, "tpl.html"), '<html><head></head><body><div id="pf2"></div></body></html>')
            msgs = []
            for check in (False, True):
                opt = JobOptions(folder=d, dest=dest, make_pdf=False, do_print=False, tpl_essence="tpl.html",
                                 app_dir=d, check_cg=check, cg_dir=d)
                self.assertFalse(run_job(opt, msgs.append))
            self.assertFalse(os.path.exists(os.path.join(d, "rapport_a_imprimer.html")))
            self.assertTrue(any("Aucun fichier de mesures .F" in m for m in msgs))


BUS_KEYS = {"1106": "01012026101010", "1206": "01012026101010", "1135": "01012026101010",
            "1235": "01012026101010", "1158": "01012026101010", "1007": "01012026101010"}


def make_truck_like(d, plate, scheme, kind_marker=True):
    old = "01012026101010"
    crc = common.checksum(old, scheme)
    f = dict(BUS_KEYS)
    f["1120"] = "500"
    if kind_marker:
        f["0320"] = ".F"
    measure_file(os.path.join(d, plate + ".F"), f, {k: crc for k in BUS_KEYS})
    o = {"0543": old, "0538": "0,50"}
    r = {"0403": old, "0401": "+00.5"}
    if kind_marker:
        o["0320"], r["0320"] = ".O", ".R"
    measure_file(os.path.join(d, plate + ".O"), o, {"0543": crc})
    measure_file(os.path.join(d, plate + ".R"), r, {"0403": crc})


class BusTruckTests(unittest.TestCase):
    def test_print_css(self):
        self.assertEqual(bus.print_css(88, -3),
                         "@media print{.page{transform-origin:0 0;transform:translateX(-27.3px) scale(0.88)}}")

    def test_truck_helpers(self):
        self.assertEqual(truck._format_slip("-03.1"), "-3,1")
        self.assertEqual(truck._format_slip("+00.5"), "+0,5")
        self.assertEqual(truck._format_slip(""), "----")
        self.assertEqual(truck._calc_imba("335", "392"), "17")
        self.assertEqual(truck._calc_imba("0", "0"), "0")
        self.assertEqual(truck._calc_imba("0", "5"), "----")

    def test_truck_update_uses_detected_crc_and_is_atomic(self):
        with tempfile.TemporaryDirectory() as d:
            make_truck_like(d, "777", "cyclic")           # le fichier prouve un CRC cyclique
            opt = JobOptions(folder=d, vehicle="camion")
            plan = truck.make_plan(opt, d, "12112026145302", lambda m: None)
            plan.update(lambda m: None)
            expected = common.checksum("12112026145302", "cyclic")
            self.assertIn("1106=%d" % expected, read(os.path.join(d, "777.F")))
            self.assertIn("1106=12112026145302", read(os.path.join(d, "777.F")))

    def test_truck_default_scheme_when_unverifiable(self):
        with tempfile.TemporaryDirectory() as d:
            make_truck_like(d, "777", "linear")
            plan = truck.make_plan(JobOptions(folder=d, vehicle="camion"), d, "12112026145302", lambda m: None)
            plan.update(lambda m: None)
            self.assertIn("1106=%d" % common.checksum("12112026145302", "linear"), read(os.path.join(d, "777.F")))

    def test_truck_rejects_wrong_type_before_modifying(self):
        with tempfile.TemporaryDirectory() as d:
            make_truck_like(d, "777", "linear", kind_marker=False)
            before = read(os.path.join(d, "777.F"))
            with self.assertRaises(common.JobError):
                truck.make_plan(JobOptions(folder=d, vehicle="camion"), d, "12112026145302", lambda m: None)
            self.assertEqual(read(os.path.join(d, "777.F")), before)

    def test_bus_requires_siblings(self):
        with tempfile.TemporaryDirectory() as d:
            measure_file(os.path.join(d, "9.F"), BUS_KEYS)
            with self.assertRaises(common.JobError):
                bus.make_plan(JobOptions(folder=d, vehicle="bus"), d, "12112026145302", lambda m: None)

    def test_guess_family(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(guess_family(d), "")
            make_truck_like(d, "777", "linear")
            self.assertEqual(guess_family(d), "bus_camion")
        with tempfile.TemporaryDirectory() as d:
            measure_file(os.path.join(d, "1.F"), {"0427": "0"})
            self.assertEqual(guess_family(d), "voiture")

    def test_run_job_truck_end_to_end(self):
        tpl = ('<html><head><style>.t{position:absolute;color:transparent}'
               '@media print{.page{margin:0;box-shadow:none;page-break-after:always;break-after:page}}'
               '</style></head><body>'
               + "".join('<div class="page"></div>' for _ in range(3)) + "</body></html>")
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as dest:
            make_truck_like(d, "777", "linear")
            write(os.path.join(d, "tpl.html"), tpl)
            opt = JobOptions(folder=d, vehicle="camion", dest=dest, make_pdf=False, do_print=False,
                             tpl_camion="tpl.html", app_dir=d, check_cg=False)
            msgs = []
            # la zone de texte du modele est absente -> erreur propre, fichiers deja mis a jour
            self.assertFalse(run_job(opt, msgs.append))
            self.assertTrue(any("absente ou ambigue" in m for m in msgs))
            self.assertTrue(os.path.isfile(os.path.join(d, "777.F")))      # rien deplace


class VehicleCheckTests(unittest.TestCase):
    def _setup(self, plate, cg_names, extra_measure=()):
        d, cg = tempfile.mkdtemp(), tempfile.mkdtemp()
        measure_file(os.path.join(d, plate + ".F"), {"0427": "0"})
        for ext in extra_measure:
            measure_file(os.path.join(d, plate + "." + ext), {"0403": "0"})
        for n in cg_names:
            write(os.path.join(cg, n), "x" * 49)
        return d, cg

    def test_found(self):
        d, cg = self._setup("0217211640", ["0217211640.cg", "0228519712.cg"])
        self.assertEqual(vehicle_check.check_vehicle(d, cg, lambda m: None), "0217211640")

    def test_registered_later_is_detected(self):
        d, cg = self._setup("0217211640", [])
        with self.assertRaises(vehicle_check.VehicleNotRegistered) as ctx:
            vehicle_check.check_vehicle(d, cg, lambda m: None)
        self.assertIn("doit d'abord etre enregistre", str(ctx.exception))
        write(os.path.join(cg, "0217211640.cg"), "x" * 49)           # ajoute apres coup
        self.assertEqual(vehicle_check.check_vehicle(d, cg, lambda m: None), "0217211640")

    def test_missing_with_close_numbers(self):
        d, cg = self._setup("0228519740", ["0228519712.cg", "1954811240.cg"])
        with self.assertRaises(common.JobError) as ctx:
            vehicle_check.check_vehicle(d, cg, lambda m: None)
        self.assertIn("0228519712.cg", str(ctx.exception))
        self.assertIn("Erreur de numerotation", str(ctx.exception))

    def test_leading_zeros_difference(self):
        d, cg = self._setup("0029519140", ["29519140.cg"])
        with self.assertRaises(common.JobError) as ctx:
            vehicle_check.check_vehicle(d, cg, lambda m: None)
        self.assertIn("29519140.cg", str(ctx.exception))

    def test_missing_without_hint(self):
        d, cg = self._setup("0000000001", ["9999999999.cg"])
        with self.assertRaises(common.JobError) as ctx:
            vehicle_check.check_vehicle(d, cg, lambda m: None)
        self.assertIn("doit d'abord etre enregistre", str(ctx.exception))
        self.assertNotIn("proches", str(ctx.exception))

    def test_measure_files_with_different_numbers(self):
        d, cg = self._setup("0217211640", ["0217211640.cg"])
        measure_file(os.path.join(d, "0217211641.G"), {"0513": "0"})
        with self.assertRaises(common.JobError) as ctx:
            vehicle_check.check_vehicle(d, cg, lambda m: None)
        self.assertIn("0217211641.G", str(ctx.exception))

    def test_cg_folder_missing(self):
        d, _ = self._setup("0217211640", [])
        with self.assertRaises(common.JobError):
            vehicle_check.check_vehicle(d, os.path.join(d, "nope"), lambda m: None)

    def test_case_insensitive_and_distance(self):
        d, cg = self._setup("0217211640", ["0217211640.CG"])
        self.assertEqual(vehicle_check.check_vehicle(d, cg, lambda m: None), "0217211640")
        self.assertEqual(vehicle_check.distance("0228519712", "0228519740"), 2)

    def test_run_job_stops_before_modifying(self):
        d, cg = self._setup("0228519740", ["0228519712.cg"])
        before = read(os.path.join(d, "0228519740.F"))
        msgs = []
        opt = JobOptions(folder=d, dest=tempfile.mkdtemp(), cg_dir=cg, make_pdf=False, do_print=False, app_dir=d)
        self.assertFalse(run_job(opt, msgs.append))
        self.assertEqual(read(os.path.join(d, "0228519740.F")), before)
        self.assertTrue(any("doit d'abord etre enregistre" in m for m in msgs))

    def test_renamed_plate_is_checked_and_rename_undone_on_failure(self):
        d, cg = self._setup("0228519740", ["0228519712.cg"])
        opt = JobOptions(folder=d, dest=tempfile.mkdtemp(), cg_dir=cg, plate="0228519741",
                         make_pdf=False, do_print=False, app_dir=d)
        msgs = []
        self.assertFalse(run_job(opt, msgs.append))
        self.assertTrue(os.path.isfile(os.path.join(d, "0228519740.F")))     # ancien nom restaure
        self.assertFalse(os.path.exists(os.path.join(d, "0228519741.F")))

    def test_renamed_plate_found_in_cg(self):
        d, cg = self._setup("0228519740", ["0228519712.cg"])
        write(os.path.join(d, "tpl.html"), '<html><head></head><body><div id="pf2"></div></body></html>')
        opt = JobOptions(folder=d, dest=tempfile.mkdtemp(), cg_dir=cg, plate="0228519712", move_files=False,
                         make_pdf=False, do_print=False, tpl_essence="tpl.html", app_dir=d)
        self.assertTrue(run_job(opt, lambda m: None))
        self.assertTrue(os.path.isfile(os.path.join(d, "0228519712.F")))


if __name__ == "__main__":
    unittest.main()
