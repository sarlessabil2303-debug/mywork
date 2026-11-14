# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import mesures_core as c  # noqa: E402


def write(path, text):
    with open(path, "wb") as fh:
        fh.write(text.encode("latin-1"))


class CoreTests(unittest.TestCase):
    def test_crc(self):
        # 14112026150918 : somme((48+d)*((pos%5)+1))
        stamp = "14112026150918"
        expected = sum((48 + int(ch)) * ((i % 5) + 1) for i, ch in enumerate(stamp))
        self.assertEqual(c.compute_crc(stamp), expected)
        self.assertEqual(c.compute_crc("00000000000000"), 48 * (1 + 2 + 3 + 4 + 5) * 2 + 48 * (1 + 2 + 3 + 4))

    def test_stamp_format(self):
        from datetime import datetime
        self.assertEqual(c.now_stamp(datetime(2026, 11, 14, 15, 9, 18)), "14112026150918")

    def test_formats(self):
        self.assertEqual(c.rip({"k": "-01.6"}, "k"), "-1.6")
        self.assertEqual(c.rip({"k": "+04.1"}, "k"), "+4.1")
        self.assertEqual(c.rip({"k": "+00.0"}, "k"), "0.0")
        self.assertEqual(c.rip_comma({"k": "-01.6"}, "k"), "-1,6")
        self.assertEqual(c.rip_comma({"k": "00.0"}, "k"), "0,0")
        self.assertEqual(c.dec({"k": "00,00"}, "k"), "0,00")
        self.assertEqual(c.dec({"k": "11,70"}, "k"), "11,70")
        self.assertEqual(c.int_of({"k": "049"}, "k"), "49")
        self.assertEqual(c.int_of({"k": "+012"}, "k"), "12")
        self.assertIsNone(c.int_of({"k": ""}, "k"))
        self.assertEqual(c.pct(1, 8), "13")       # 12.5 -> arrondi vers le haut
        self.assertIsNone(c.pct(5, 0))

    def test_update_measure_files(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "123.F")
            write(p, "[ENTETE]\r\n0427=keep\r\n[MESURES]\r\n0427=old\r\n0450=old\r\n0420=361\r\n[CRC]\r\n0468=1\r\n0427=2\r\n")
            n = c.update_measure_files(d, "14112026150918", 4321, lambda m: None)
            self.assertEqual(n, 1)
            with open(p, "rb") as fh:
                data = fh.read().decode("latin-1")
            self.assertEqual(
                data,
                "[ENTETE]\r\n0427=keep\r\n[MESURES]\r\n0427=14112026150918\r\n0450=14112026150918\r\n"
                "0420=361\r\n[CRC]\r\n0468=4321\r\n0427=4321\r\n")

    def test_mode(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(c.detect_mode(d), c.MODE_ESSENCE)
            write(os.path.join(d, "a.O"), "[MESURES]\r\n")
            self.assertEqual(c.detect_mode(d), c.MODE_GAZOLE)
            write(os.path.join(d, "a.G"), "[MESURES]\r\n")
            self.assertEqual(c.detect_mode(d), c.MODE_ESSENCE)

    def test_report_essence_mini(self):
        tpl = ('<html><head></head><body><div id="pf1">'
               '<div class="t m0 x2 h1 y3 ff1">Date: <span>09/09/2026</span> </div>'
               '<div class="t m0 x5 h1 y15 ff1">0.0 m/km</div></div>'
               '<div id="pf2"><div class="t m0 x4 h1 yd ff1">: 111</div></div></body></html>')
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "tpl.html"), tpl)
            write(os.path.join(d, "777.F"), "[MESURES]\r\n0426=1\r\n")
            write(os.path.join(d, "777.R"), "[MESURES]\r\n0401=+00.7\r\n")
            msgs = []
            c.build_report_essence(d, "14112026150918", os.path.join(d, "tpl.html"),
                                   os.path.join(d, "out.html"), msgs.append)
            with open(os.path.join(d, "out.html"), encoding="utf-8") as fh:
                out = fh.read()
            self.assertIn("14/11/2026", out)
            self.assertNotIn("09/09/2026", out)
            self.assertIn("+0.7", out)
            self.assertIn(">777<", out)
            self.assertIn(".nv{", out)

    def test_move(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as dest:
            write(os.path.join(d, "a.F"), "x")
            write(os.path.join(d, "a.o"), "x")
            write(os.path.join(dest, "a.F"), "old")
            c.move_measure_files(d, dest, ("F", "O"), lambda m: None)
            self.assertEqual(sorted(os.listdir(dest)), ["a.F", "a.o"])
            self.assertEqual(os.listdir(d), [])

    def test_run_job_without_pdf(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as dest:
            write(os.path.join(d, "tpl.html"),
                  '<html><head></head><body><div id="pf2"></div></body></html>')
            write(os.path.join(d, "5.F"), "[MESURES]\r\n0427=0\r\n[CRC]\r\n0468=0\r\n")
            opt = c.JobOptions(folder=d, dest=dest, make_pdf=False, do_print=False,
                               tpl_essence="tpl.html", app_dir=d)
            msgs = []
            self.assertTrue(c.run_job(opt, msgs.append))
            self.assertTrue(os.path.isfile(os.path.join(d, c.REPORT_NAME)))
            self.assertTrue(os.path.isfile(os.path.join(dest, "5.F")))


if __name__ == "__main__":
    unittest.main()
