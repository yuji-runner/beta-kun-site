import pathlib
import unittest


HTML = pathlib.Path(__file__).with_name("search.html").read_text(encoding="utf-8")


class PediatricDoseUiContractTests(unittest.TestCase):
    def test_starting_cap_has_starting_semantics(self):
        self.assertIn('data.starting_regimen.role === "starting"', HTML)
        self.assertIn("<h3>開始量上限</h3>", HTML)
        self.assertIn('renderDoseField("開始用量に適用された上限"', HTML)
        self.assertIn('"開始量上限適用後"', HTML)

    def test_nonautomatic_maximum_is_separate(self):
        self.assertIn('option.id === "nonautomatic_maximum_regimen"', HTML)
        self.assertIn('"最大投与量（自動適用なし）"', HTML)
        self.assertIn('"体重による最大投与量計算値"', HTML)
        self.assertIn('"最大投与量"', HTML)
        self.assertIn("最大投与量は開始量へ自動適用されません。", HTML)

    def test_product_options_preserve_formal_product_identity(self):
        self.assertIn("function productOptionsFromContexts(contexts)", HTML)
        self.assertIn("product.product_id", HTML)
        self.assertIn("product.product_name", HTML)
        self.assertIn("payload.product_id = selectedOptionMeta.product_id", HTML)
        self.assertIn(
            "const selectableForms = productOptions.length > 1 ? productOptions : dosageForms",
            HTML,
        )

    def test_no_ingredient_specific_branch(self):
        self.assertNotIn('ingredientName === "アジルサルタン"', HTML)
        self.assertNotIn('data.ingredient_name === "アジルサルタン"', HTML)


if __name__ == "__main__":
    unittest.main()
