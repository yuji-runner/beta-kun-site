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
        self.assertNotIn('ingredientName === "フレカイニド酢酸塩"', HTML)
        self.assertNotIn('data.ingredient_name === "フレカイニド酢酸塩"', HTML)

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

    def test_bsa_is_an_explicit_conditional_input(self):
        self.assertIn('id="doseBsaFields"', HTML)
        self.assertIn('id="doseBsaInput"', HTML)
        self.assertIn('requiredInputs.includes("body_surface_area")', HTML)
        self.assertIn("payload.body_surface_area_m2 = bodySurfaceAreaValue", HTML)
        self.assertIn("身長・体重からの自動算出は行いません", HTML)

    def test_bsa_usual_and_maximum_regimens_are_separate(self):
        self.assertIn('data.dose_basis === "mg_per_m2_per_day"', HTML)
        self.assertIn('"原典の通常用量"', HTML)
        self.assertIn('"1日最高用量（自動適用なし）"', HTML)
        self.assertIn('"計算後の1日最高用量"', HTML)
        self.assertIn("最大用量は${primaryRegimenObjectLabel}へ自動適用されません。", HTML)

    def test_bsa_frequency_range_does_not_create_per_dose_output(self):
        self.assertIn("data.administration_interval.frequency_min", HTML)
        self.assertIn("data.administration_interval.frequency_max", HTML)
        self.assertIn("1日量から1回量を自動計算せず", HTML)
        self.assertIn("2回又は3回を自動選択しません", HTML)

    def test_bsa_product_is_optional_and_daily_conversion_is_label_explicit(self):
        self.assertIn('optionalContexts.includes("product")', HTML)
        self.assertIn("const products = isBsaDailyRule", HTML)
        self.assertIn('"通常1日製剤量（原典明示換算）"', HTML)
        self.assertIn("maximum_daily_product_conversion", HTML)
        self.assertIn("1回量・分包量へ自動分割しません", HTML)

    def test_multirole_regimens_are_rendered_separately(self):
        self.assertIn("data.maintenance_regimen", HTML)
        self.assertIn("data.maximum_daily_regimen", HTML)
        self.assertIn("data.titration_regimen", HTML)
        self.assertIn("維持用量（自動切替なし）", HTML)
        self.assertIn("1日最高用量（自動適用なし）", HTML)
        self.assertIn("増量方法（自動適用なし）", HTML)
        self.assertIn("維持用量への切替は自動判定しません", HTML)
        self.assertIn("増量日・次回用量を自動判定せず", HTML)

    def test_regimen_product_conversion_is_daily_only(self):
        self.assertIn("data.regimen_product_conversions", HTML)
        self.assertIn("hasRegimenProductConversions", HTML)
        self.assertIn("1日製剤量（原典明示換算）", HTML)
        self.assertIn("添付文書に明示された1日量換算", HTML)
        self.assertIn("1回製剤量・分包量・丸めは自動生成しません", HTML)
        self.assertNotIn("regimenProductConversions[role].per_administration_quantity", HTML)

    def test_optional_products_reappear_after_indication_selection(self):
        self.assertIn("showProductsForSelectedRoute(route, requireSelection = true)", HTML)
        self.assertIn('stage6.optional_contexts.includes("product")', HTML)
        self.assertIn("showProductsForSelectedRoute(routes[0], false)", HTML)
        self.assertIn("doseRequiredContexts.filter", HTML)


if __name__ == "__main__":
    unittest.main()
