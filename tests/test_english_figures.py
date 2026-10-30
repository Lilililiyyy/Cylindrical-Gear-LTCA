"""英文图表验证：类别刻度重绘不退回中文，翻译不改变数值和单位。"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

PROJECT = next(p for p in Path(__file__).resolve().parents
               if (p/"pyproject.toml").is_file() and (p/"gear_contact").is_dir())
SPEC = importlib.util.spec_from_file_location("english_figures", PROJECT/"examples/generate_english_figures.py")
ENGLISH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENGLISH)


class EnglishFigureTests(unittest.TestCase):
    def test_dynamic_label_preserves_numbers_and_units_and_rejects_missing_translation(self):
        translated = ENGLISH.translate_text("本项目：峰压 186.5 MPa")
        self.assertIn("186.5 MPa", translated)
        self.assertNotRegex(translated, r"[\u3400-\u9fff]")
        with self.assertRaises(ValueError):
            ENGLISH.translate_text("未定义的图表标签")

    def test_category_tick_formatter_remains_english_after_canvas_redraw(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.figure import Figure
        original_save = Figure.savefig
        fig, ax = plt.subplots()
        ax.set_yticks([0, 1], ["中心距 a", "小轮分度圆直径"])
        ax.set_xlabel("数值 / mm")
        with tempfile.TemporaryDirectory() as directory:
            with ENGLISH.english_figure_labels():
                fig.savefig(Path(directory)/"labels.png")
                fig.canvas.draw()
                self.assertEqual([label.get_text() for label in ax.get_yticklabels()],
                                 ["Centre distance a", "Pinion reference diameter"])
                self.assertEqual(ax.get_xlabel(), "Value / mm")
        self.assertIs(Figure.savefig, original_save)
        plt.close(fig)


if __name__ == "__main__":
    unittest.main()
