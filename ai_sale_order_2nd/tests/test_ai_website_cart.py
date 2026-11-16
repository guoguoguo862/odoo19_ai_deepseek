from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.website_sale.tests.common import MockRequest


@tagged("post_install", "-at_install")
class TestAIWebsiteCart(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Fresh databases can leave the base language's active flag unset.
        # Keep the bilingual catalog test deterministic across test databases.
        cls.env["res.lang"].with_context(active_test=False).search([
            ("code", "=", "en_US"),
        ]).write({"active": True})
        cls.env = cls.env(context=dict(cls.env.context, lang="en_US"))
        cls.website = cls.env["website"].create({
            "name": "AI cart regression website",
            "company_id": cls.env.company.id,
            "ecommerce_access": "everyone",
            "prevent_zero_price_sale": False,
        })
        cls.other_website = cls.env["website"].create({
            "name": "Other AI cart regression website",
            "company_id": cls.env.company.id,
        })
        cls.public_user = cls.website.user_id

        def make_product(name, code, **values):
            return cls.env["product.product"].create({
                "name": name,
                "default_code": code,
                "type": "service",
                "list_price": 20,
                "sale_ok": True,
                "is_published": True,
                "website_id": cls.website.id,
                **values,
            })

        cls.desk_one = make_product("AI Cart Desk One", "AI-CART-DESK-ONE")
        cls.desk_two = make_product("AI Cart Desk Two", "AI-CART-DESK-TWO")
        cls.hidden_product = make_product(
            "AI Cart Hidden", "AI-CART-HIDDEN", is_published=False,
        )
        cls.other_product = make_product(
            "AI Cart Other Website", "AI-CART-OTHER", website_id=cls.other_website.id,
        )
        attribute = cls.env["product.attribute"].create({
            "name": "AI Cart Upholstery",
            "create_variant": "always",
            "value_ids": [
                Command.create({"name": "Velvet"}),
                Command.create({"name": "Leather"}),
            ],
        })
        cls.sofa = cls.env["product.template"].create({
            "name": "AI Cart Two-Seat Sofa",
            "type": "service",
            "list_price": 100,
            "sale_ok": True,
            "is_published": True,
            "website_id": cls.website.id,
            "attribute_line_ids": [Command.create({
                "attribute_id": attribute.id,
                "value_ids": [Command.set(attribute.value_ids.ids)],
            })],
        })
        cls.velvet = cls.sofa.product_variant_ids.filtered(
            lambda p: "Velvet" in p.product_template_attribute_value_ids.mapped("name")
        )
        cls.website = cls.website.with_user(cls.public_user).with_context(
            website_id=cls.website.id, lang="en_US",
        )
        cls.agent = cls.website.env["ai.agent"]

    def _request(self, cart=None):
        return MockRequest(
            self.website.env,
            website=self.website,
            context=self.website.env.context,
            sale_order_id=cart.id if cart else None,
        )

    def _expect_user_error(self, callback):
        # TransactionCase.assertRaises creates its own savepoint. Catch directly
        # so these assertions exercise the tool's rollback, not the test helper.
        try:
            callback()
        except UserError:
            return
        self.fail("The cart tool should have rejected the request")

    def _cart_lines(self, cart):
        return sorted(
            (line.id, line.product_id.id, line.product_uom_qty)
            for line in cart.order_line
        )

    def test_variant_display_names_and_internal_reference(self):
        with self._request():
            self.agent._ai_prepare_website_sale_request(self.website)
            for name in ("AI Cart Two-Seat Sofa (Velvet)", "AI Cart Two-Seat Sofa Velvet"):
                with self.subTest(name=name):
                    product = self.agent._ai_find_sale_product(name, website=self.website)
                    self.assertEqual(product.id, self.velvet.id)
            product = self.agent._ai_find_sale_product(
                self.desk_one.default_code, website=self.website,
            )
            self.assertEqual(product.id, self.desk_one.id)

    def test_bare_template_name_remains_ambiguous(self):
        with self._request():
            self.agent._ai_prepare_website_sale_request(self.website)
            with self.assertRaises(ValidationError):
                self.agent._ai_find_sale_product(self.sofa.name, website=self.website)

    def test_unpublished_and_other_website_products_are_excluded(self):
        with self._request():
            self.agent._ai_prepare_website_sale_request(self.website)
            for product in (self.hidden_product, self.other_product):
                with self.subTest(product=product.default_code), self.assertRaises(UserError):
                    self.agent._ai_find_sale_product(
                        product.default_code, website=self.website,
                    )

    def test_successful_batch_adds_all_products_and_verifies_once(self):
        Order = type(self.env["sale.order"])
        original_verify = Order._verify_cart_after_update
        verified_orders = []

        def verify(order):
            verified_orders.append(order.id)
            return original_verify(order)

        with self._request() as request, patch.object(Order, "_verify_cart_after_update", verify):
            result = self.agent._ai_tool_add_products_to_website_cart(
                [self.desk_one.default_code, self.desk_two.default_code, "AI Cart Two-Seat Sofa Velvet"],
                [1, 2, 3],
            )
            cart = request.cart
            quantities = {line.product_id.id: line.product_uom_qty for line in cart.order_line}
            self.assertEqual(quantities, {
                self.desk_one.id: 1,
                self.desk_two.id: 2,
                self.velvet.id: 3,
            })
            self.assertEqual(verified_orders, [cart.id])
            self.assertEqual(request.session["website_sale_cart_quantity"], 6)
            self.assertIn("Velvet", result)

    def test_invalid_third_product_keeps_existing_cart_unchanged(self):
        with self._request() as request:
            self.agent._ai_tool_add_products_to_website_cart([self.desk_one.default_code], [4])
            cart = request.cart
            before = self._cart_lines(cart)
            self._expect_user_error(lambda: self.agent._ai_tool_add_products_to_website_cart(
                [self.desk_one.default_code, self.desk_two.default_code, "AI-CART-MISSING"],
                [1, 1, 1],
            ))
            self.assertEqual(self._cart_lines(cart), before)
            self.assertEqual(request.session["website_sale_cart_quantity"], 4)

    def test_second_add_failure_rolls_back_first_add(self):
        Order = type(self.env["sale.order"])
        original_add = Order._cart_add

        def fail_second_add(order, product_id, quantity=1.0, **kwargs):
            if product_id == self.desk_two.id:
                raise UserError("Simulated cart update failure")
            return original_add(order, product_id, quantity, **kwargs)

        with self._request() as request:
            self.agent._ai_tool_add_products_to_website_cart([self.desk_one.default_code], [4])
            cart = request.cart
            before = self._cart_lines(cart)
            with patch.object(Order, "_cart_add", fail_second_add):
                self._expect_user_error(lambda: self.agent._ai_tool_add_products_to_website_cart(
                    [self.desk_one.default_code, self.desk_two.default_code], [2, 1],
                ))
            self.assertEqual(self._cart_lines(cart), before)
            self.assertEqual(request.cart.id, cart.id)
            self.assertEqual(request.session["website_sale_cart_quantity"], 4)

    def test_new_cart_failure_restores_session(self):
        Order = type(self.env["sale.order"])
        with self._request() as request:
            self.assertFalse(request.cart)
            count_before = self.env["sale.order"].search_count([])
            session_before = {
                key: (key in request.session, request.session.get(key))
                for key in ("sale_order_id", "website_sale_cart_quantity")
            }
            with patch.object(
                Order, "_verify_cart_after_update",
                side_effect=UserError("Simulated final cart validation failure"),
            ):
                self._expect_user_error(lambda: self.agent._ai_tool_add_products_to_website_cart(
                    [self.desk_one.default_code], [1],
                ))
            self.assertEqual(self.env["sale.order"].search_count([]), count_before)
            self.assertFalse(request.cart)
            self.assertEqual({
                key: (key in request.session, request.session.get(key))
                for key in session_before
            }, session_before)

    def test_invalid_quantities_do_not_create_a_cart(self):
        for quantity in (0.5, 0, -1):
            with self.subTest(quantity=quantity), self._request() as request:
                count_before = self.env["sale.order"].search_count([])
                self._expect_user_error(lambda: self.agent._ai_tool_add_products_to_website_cart(
                    [self.desk_one.default_code], [quantity],
                ))
                self.assertFalse(request.cart)
                self.assertEqual(self.env["sale.order"].search_count([]), count_before)

    def test_partial_variant_name_keeps_unspecified_attributes(self):
        color = self.env["product.attribute"].create({
            "name": "AI Catalog Color",
            "create_variant": "always",
            "value_ids": [Command.create({"name": "White"}), Command.create({"name": "Black"})],
        })
        legs = self.env["product.attribute"].create({
            "name": "AI Catalog Legs",
            "create_variant": "always",
            "value_ids": [Command.create({"name": "Steel"}), Command.create({"name": "Wood"})],
        })
        desk = self.env["product.template"].create({
            "name": "AI Catalog Partial Desk",
            "type": "service",
            "list_price": 40,
            "sale_ok": True,
            "is_published": True,
            "website_id": self.website.id,
            "attribute_line_ids": [Command.create({
                "attribute_id": attribute.id,
                "value_ids": [Command.set(attribute.value_ids.ids)],
            }) for attribute in (color, legs)],
        })
        white_steel = desk.product_variant_ids.filtered(
            lambda p: set(p.product_template_attribute_value_ids.mapped("name")) == {"White", "Steel"}
        )
        black_wood = desk.product_variant_ids.filtered(
            lambda p: set(p.product_template_attribute_value_ids.mapped("name")) == {"Black", "Wood"}
        )
        (desk.product_variant_ids - white_steel - black_wood).write({"active": False})
        with self._request():
            self.agent._ai_prepare_website_sale_request(self.website)
            product = self.agent._ai_find_sale_product(
                "White AI Catalog Partial Desk", website=self.website,
            )
            self.assertEqual(product.id, white_steel.id)
            self.assertIn("Steel", product.display_name)

    def test_partial_variant_name_reports_candidates_when_ambiguous(self):
        with self._request():
            self.agent._ai_prepare_website_sale_request(self.website)
            with self.assertRaises(ValidationError) as caught:
                self.agent._ai_find_sale_product("AI Cart Sofa", website=self.website)
            self.assertIn("Velvet", str(caught.exception))
            self.assertIn("Leather", str(caught.exception))

    def test_catalog_search_returns_real_references_and_website_products(self):
        with self._request():
            for query in ("Desk One", self.desk_one.default_code):
                with self.subTest(query=query):
                    result = self.agent._ai_tool_search_website_products(query)
                    self.assertEqual([p["product_id"] for p in result["products"]], [self.desk_one.id])
                    self.assertEqual(result["products"][0]["reference"], self.desk_one.default_code)
                    self.assertIn("Desk One", result["products"][0]["catalog_name"])
                    self.assertFalse(result["has_more"])
            result = self.agent._ai_tool_search_website_products("AI Cart")
            ids = {p["product_id"] for p in result["products"]}
            self.assertIn(self.desk_one.id, ids)
            self.assertIn(self.velvet.id, ids)
            self.assertNotIn(self.hidden_product.id, ids)
            self.assertNotIn(self.other_product.id, ids)

    def test_catalog_search_uses_english_names_in_chinese_context(self):
        self.env.ref("base.lang_zh_CN").write({"active": True})
        self.sofa.with_context(lang="zh_CN").write({"name": "测试绒布沙发"})
        velvet_value = self.velvet.product_template_attribute_value_ids.product_attribute_value_id
        velvet_value.with_context(lang="zh_CN").write({"name": "绒布"})
        website = self.website.with_context(lang="zh_CN")
        with MockRequest(website.env, website=website, context=website.env.context):
            result = website.env["ai.agent"]._ai_tool_search_website_products("AI Cart Two-Seat Sofa Velvet")
            self.assertEqual([p["product_id"] for p in result["products"]], [self.velvet.id])
            self.assertIn("Velvet", result["products"][0]["catalog_name"])
            self.assertIn("绒布", result["products"][0]["name"])
            bilingual = website.env["ai.agent"]._ai_tool_search_website_products(
                "测试绒布沙发 Velvet Sofa",
            )
            self.assertEqual([p["product_id"] for p in bilingual["products"]], [self.velvet.id])

    def test_catalog_search_does_not_create_cart_or_change_order_lines(self):
        with self._request() as request:
            order_count = self.env["sale.order"].search_count([])
            line_count = self.env["sale.order.line"].search_count([])
            result = self.agent._ai_tool_search_website_products("AI Cart Velvet Sofa")
            self.assertEqual([p["product_id"] for p in result["products"]], [self.velvet.id])
            self.assertFalse(request.cart)
            self.assertNotIn("sale_order_id", request.session)
            self.assertEqual(self.env["sale.order"].search_count([]), order_count)
            self.assertEqual(self.env["sale.order.line"].search_count([]), line_count)

    def test_catalog_search_reports_more_results(self):
        self.env["product.product"].create([{
            "name": "AI Catalog Pagination %s" % index,
            "type": "service",
            "sale_ok": True,
            "list_price": 5,
            "is_published": True,
            "website_id": self.website.id,
        } for index in range(11)])
        with self._request():
            result = self.agent._ai_tool_search_website_products("AI Catalog Pagination")
            self.assertEqual(len(result["products"]), 10)
            self.assertTrue(result["has_more"])
