"""Testes do launcher e das ferramentas (sem GPU, sem disco do jogo, sem rede).

Rodar:  QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = tempfile.mkdtemp(prefix="mmx5test_")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["MMX5_GAME_DIR"] = str(Path(TMP) / "game")
os.environ["XDG_CONFIG_HOME"] = str(Path(TMP) / "cfg")
sys.path[:0] = [str(ROOT / "launcher"), str(ROOT / "tools")]

import gpuinfo  # noqa: E402
import launcher as L  # noqa: E402
import padmap  # noqa: E402


def fresh_game_dir() -> Path:
    d = Path(tempfile.mkdtemp(dir=TMP))
    L.GAME_DIR = d
    return d


class TomlAndConfig(unittest.TestCase):
    def test_toml_roundtrip(self):
        data = {"video": {"renderer": "opengl", "scale": 0.35, "on": True},
                "feature": [{"id": "a", "values": {"k": "v"}}, {"id": "b"}], "top": 3}
        self.assertEqual(tomllib.loads(L.dump_toml(data)), data)

    def test_game_config_state(self):
        d = fresh_game_dir()
        cfg = L.GameConfig(d)
        cfg.set("video", "renderer", "opengl")
        cfg.set_feature(L.MOD_PKG_WIDE, True)
        cfg.set_feature_value(L.MOD_PKG_WIDE, "aspect", "16:10")
        cfg.set_feature_resource(L.MOD_PKG_HD, "pack", "/x/y")
        cfg.save()
        c2 = L.GameConfig(d)
        self.assertTrue(c2.feature_enabled(L.MOD_PKG_WIDE))
        self.assertEqual(c2.feature_value(L.MOD_PKG_WIDE, "aspect", ""), "16:10")
        self.assertEqual(c2.feature_resource(L.MOD_PKG_HD, "pack"), "/x/y")
        self.assertEqual(c2.get("video", "renderer"), "opengl")

    def test_p1_device(self):
        d = fresh_game_dir()
        cfg = L.GameConfig(d)
        for choice, want in (("keyboard", "keyboard"), ("controller", "auto")):
            L.write_launch_env({"MMX5_P1_INPUT": choice})
            self.assertEqual(L.apply_p1_device(cfg), want)
        self.assertEqual(cfg.get("controller", "p1_device"), "auto")

    def test_offer_vulkan(self):
        d = fresh_game_dir()
        (d / "game.toml").write_text("[video]\nx = 1\n")
        L.ensure_offer_vulkan()
        L.ensure_offer_vulkan()
        txt = (d / "game.toml").read_text()
        self.assertEqual(txt.count("offer_vulkan = true"), 1)
        self.assertEqual(tomllib.loads(txt)["video"]["offer_vulkan"], True)


class Mods(unittest.TestCase):
    GOOD = {"type": "patch", "name": "T",
            "options": [{"id": "on", "type": "boolean", "default": True},
                        {"id": "m", "type": "choice", "default": "a",
                         "choices": [{"value": "a", "label": "A"}, {"value": "b"}]},
                        {"id": "n", "type": "integer", "min": 1, "max": 9, "default": 3}],
            "patches": [{"address": "0x8001DE64", "expected": "02 00 02 24", "replace": "09 00 02 24",
                         "when": {"m": "a"}}]}

    def test_validate_ok_and_manifest(self):
        self.assertEqual(L.validate_patch_mod(self.GOOD), "")
        m = L.ModInfo("ext:t", "T", "1.0.0", "x", "d", "", "toggle", ("user.t", "1.0.0", "main"))
        m.ext = self.GOOD
        man = tomllib.loads(L.dump_toml(L.build_manifest(m)))
        self.assertEqual(man["patch"][0]["expected"], "02 00 02 24")
        self.assertEqual(man["patch"][0]["when"], {"m": "a"})
        self.assertEqual(len(man["option"]), 3)
        self.assertEqual(man["option"][1]["choice"][0]["value"], "a")

    def test_validate_errors(self):
        bad = dict(self.GOOD, patches=[{"address": "0x1", "expected": "00", "replace": "00"}])
        self.assertIn("fora de", L.validate_patch_mod(bad))
        bad = dict(self.GOOD, patches=[{"address": "0x80010000", "expected": "00 00", "replace": "00"}])
        self.assertIn("mesmo tamanho", L.validate_patch_mod(bad))
        bad = dict(self.GOOD, patches=[{"address": "0x80010000", "expected": "00", "replace": "00",
                                        "when": {"nope": "1"}}])
        self.assertIn("não existe", L.validate_patch_mod(bad))
        self.assertIn("nenhum patch", L.validate_patch_mod({"options": [], "patches": []}))

    def test_parse_mod_cases(self):
        d = Path(tempfile.mkdtemp(dir=TMP))
        (d / "broken").mkdir()
        (d / "broken" / "mod.json").write_text('{ "type": ')
        (d / "weird").mkdir()
        (d / "weird" / "mod.json").write_text('{"type": "magia"}')
        (d / "bez").mkdir()
        (d / "bez" / "mod.json").write_text('{"type": "bezel", "artwork": "nao.png"}')
        self.assertIn("inválido", L.parse_mod(d / "broken").error)
        self.assertIn("desconhecido", L.parse_mod(d / "weird").error)
        self.assertIn("não encontrada", L.parse_mod(d / "bez").error)
        self.assertIsNone(L.parse_mod(d))

    def test_shipped_mods_are_valid(self):
        mods = {p.name: L.parse_mod(p) for p in (ROOT / "mods").iterdir() if (p / "mod.json").exists()}
        self.assertEqual(set(mods), {"hd-texturas", "exemplo-bezel", "exemplo-patch"})
        for name, m in mods.items():
            self.assertEqual(m.error, "", f"{name}: {m.error}")
        self.assertTrue(mods["exemplo-patch"].template)
        self.assertTrue((ROOT / "mods" / "hd-texturas" / "config.yaml").exists())

    def test_compile_patch_mods_writes_package(self):
        d = fresh_game_dir()
        m = L.ModInfo("ext:t", "T", "1.0.0", "x", "d", "", "toggle", ("user.t", "1.0.0", "main"))
        m.mtype, m.ext = "patch", self.GOOD
        L.compile_patch_mods([m])
        f = d / "mods" / "installed" / "user.t" / "1.0.0" / "manifest.toml"
        self.assertTrue(f.exists())
        L.compile_patch_mods([])               # mod removido -> pacote some
        self.assertFalse(f.exists())


class HdTextures(unittest.TestCase):
    def test_disk_state_and_report(self):
        d = fresh_game_dir()
        self.assertFalse(L.hd_disk_state(d)["present"])
        cfg = L.GameConfig(d)
        cfg.set_feature(L.MOD_PKG_HD, False)
        cfg.set_feature_value(L.MOD_PKG_HD, "dump", "true")
        cfg.save()
        st = L.hd_disk_state(d)
        self.assertTrue(st["present"] and not st["enabled"] and st["dump"] == "true")
        (d / "last_run.log").write_text("psxrecomp: main() entered\n")
        self.assertIn("NÃO estava ligado", L.hd_run_report(None))
        (d / "last_run.log").write_text("psxrecomp: HD textures: /p (replacements on, dumping on)\n")
        self.assertIn("ATIVAS", L.hd_run_report(None))

    def test_wide_capture_config(self):
        p = Path(tempfile.mkdtemp(dir=TMP))
        L.set_pack_wide(p, True)
        self.assertTrue(L.pack_wide(p))
        L.set_pack_wide(p, False)
        self.assertFalse((p / "config.yaml").exists())


class GpuAndInput(unittest.TestCase):
    FAKE = [dict(id="0000:00:02.0", name="iGPU", vendor_id=0x8086, device_id=0x9A49, driver="i915",
                 primary=True, kind="integrada"),
            dict(id="0000:01:00.0", name="NV", vendor_id=0x10DE, device_id=0x2503, driver="nvidia",
                 primary=False, kind="dedicada"),
            dict(id="0000:03:00.0", name="AMD", vendor_id=0x1002, device_id=0x73FF, driver="amdgpu",
                 primary=False, kind="dedicada")]

    def test_gpu_env(self):
        self.assertEqual(gpuinfo.gpu_env("auto", self.FAKE), {})
        self.assertEqual(gpuinfo.gpu_env("cpu", self.FAKE)["LIBGL_ALWAYS_SOFTWARE"], "1")
        nv = gpuinfo.gpu_env("0000:01:00.0", self.FAKE)
        self.assertEqual(nv["__NV_PRIME_RENDER_OFFLOAD"], "1")
        amd = gpuinfo.gpu_env("0000:03:00.0", self.FAKE)
        self.assertEqual(amd["DRI_PRIME"], "pci-0000_03_00_0")
        self.assertEqual(amd["MESA_VK_DEVICE_SELECT"], "1002:73ff")
        self.assertTrue(set(amd) <= set(gpuinfo.GPU_ENV_KEYS) and set(nv) <= set(gpuinfo.GPU_ENV_KEYS))

    def test_padmap_guid_and_mapping(self):
        # GUID SDL conhecido do "USB Gamepad" generico (DragonRise 0079:0011)
        self.assertEqual(padmap.make_guid(3, 0x0079, 0x0011, 0x0110), "03000000790000001100000010010000")
        self.assertEqual(padmap.src_string(dict(kind="b", idx=2), "button"), "b2")
        self.assertEqual(padmap.src_string(dict(kind="h", idx=0, mask=8), "button"), "h0.8")
        self.assertEqual(padmap.src_string(dict(kind="a", idx=1, sign=-1), "button"), "-a1")
        self.assertEqual(padmap.src_string(dict(kind="a", idx=0, sign=-1), "stick"), "a0~")
        m = padmap.build_mapping("g", "Meu, Pad", {"a": "b0"})
        self.assertEqual(m, "g,Meu  Pad,platform:Linux,a:b0")


class Art(unittest.TestCase):
    def test_placeholder_art_and_captions(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        for n in ("zero", "x", "sigma"):
            self.assertFalse(L.load_art(n).isNull())
        self.assertEqual(L.art_captions()["zero"], ("", ""))


class Upscaler(unittest.TestCase):
    def test_alpha_classes_and_names(self):
        import numpy as np
        from PIL import Image
        import upscale_textures as U
        a = np.zeros((16, 24, 4), np.uint8)
        a[3:13, 4:20, :3] = np.random.default_rng(1).integers(0, 255, (10, 16, 3))
        a[3:13, 4:20, 3] = 255
        a[5:8, 6:9, 3] = 143
        for mode in (U.m_lanczos, U.m_scale2x):
            for s in (2, 3, 4):
                out = mode(a, s)
                self.assertEqual(out.shape[:2], (16 * s, 24 * s))
                self.assertTrue(set(np.unique(out[..., 3]).tolist()) <= {0, 143, 255})
        pack = Path(tempfile.mkdtemp(dir=TMP))
        (pack / "dumps").mkdir()
        Image.fromarray(a).save(pack / "dumps" / "texpage-P4-AAAA-BBBB-64x256-0-0-12x12-P0-15.png")
        sys.argv = ["x", "--pack", str(pack), "--scale", "2", "--mode", "scale2x"]
        self.assertEqual(U.main(), 0)
        self.assertTrue((pack / "replacements" / "texpage-P4-AAAA-BBBB-64x256-0-0-12x12-P0-15.png").exists())


class Scripts(unittest.TestCase):
    def test_patch_file_is_well_formed(self):
        p = (ROOT / "patches" / "0001-widescreen-aspect-option.patch").read_text()
        self.assertIn("mmx5_widescreen_plugin.c", p)
        self.assertIn('id = "aspect"', p)
        self.assertNotIn("\t20", p)            # sem timestamps nos cabecalhos

    def test_version_is_1_0_0(self):
        self.assertEqual(L.VERSION, "1.0.0")
        self.assertIn("1.0.0", (ROOT / "CHANGELOG.md").read_text())


if __name__ == "__main__":
    unittest.main()
