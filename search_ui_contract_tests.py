import pathlib
import unittest


HTML = pathlib.Path(__file__).with_name("search.html").read_text(encoding="utf-8")


class PediatricDoseUiContractTests(unittest.TestCase):
    def test_starting_cap_has_starting_semantics(self):
        self.assertIn('regimenRole === "starting"', HTML)
        self.assertIn("<h3>開始量上限</h3>", HTML)
        self.assertIn('renderDoseField("開始用量に適用された上限"', HTML)
        self.assertIn('`${primaryRegimenLabel}上限適用後`', HTML)

    def test_primary_regimen_label_uses_common_role_semantics(self):
        self.assertIn('regimenRole === "starting"', HTML)
        self.assertIn('regimenRole === "maintenance"', HTML)
        self.assertIn('regimenRole === "usual" || regimenRole === "primary"', HTML)
        self.assertIn('? "維持用量"', HTML)
        self.assertIn('? "通常用量"', HTML)
        self.assertIn(': "開始量"', HTML)
        self.assertIn(
            'renderDoseMetric(dailyLimitApplied ? `${primaryRegimenLabel}計算値` : primaryRegimenLabel',
            HTML,
        )

    def test_nonautomatic_maximum_is_separate(self):
        self.assertIn('option.id === "nonautomatic_maximum_regimen"', HTML)
        self.assertIn('"最大投与量（自動適用なし）"', HTML)
        self.assertIn('"体重による最大投与量計算値"', HTML)
        self.assertIn('"最大投与量"', HTML)
        self.assertIn("最大投与量は${primaryRegimenObjectLabel}へ自動適用されません。", HTML)

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

    def test_stage5_subsequent_regimen_is_explicit_and_nonautomatic(self):
        self.assertIn("function renderSubsequentRegimen(regimen)", HTML)
        self.assertIn('regimen.role !== "subsequent_usual"', HTML)
        self.assertIn("後続の通常用量（自動移行なし）", HTML)
        self.assertIn("この後続用量へは自動移行しません。", HTML)

    def test_nonautomatic_fixed_dose_titration_is_separate(self):
        self.assertIn("function renderNonautomaticDoseTitration(titration, rule)", HTML)
        self.assertIn("適宜増減・1日最高用量（自動適用なし）", HTML)
        self.assertIn('renderDoseField("1日最高用量"', HTML)
        self.assertIn("最高用量への移行は自動適用されません。", HTML)


if __name__ == "__main__":
    unittest.main()
