# -*- coding: utf-8 -*-

import re
from math import isfinite

from odoo import _, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.http import request


class AIAgent(models.Model):
    _inherit = "ai.agent"

    def _ai_tool_create_sale_order(self, product_names, quantities, note=False):
        """Create a draft sale order for the current user's partner."""
        partner = self.env.user.partner_id
        if not partner:
            raise UserError(_("The current user has no related customer."))
        if not product_names:
            raise UserError(_("Please provide at least one product to create a quotation."))
        if len(product_names) != len(quantities):
            raise UserError(_("Product names and quantities must have the same number of items."))

        order_lines = []
        line_summaries = []
        for product_name, quantity in zip(product_names, quantities):
            product_name = (product_name or "").strip()

            if not product_name:
                raise UserError(_("Each order line must include a product name."))
            if quantity is None or quantity <= 0:
                raise UserError(_("The quantity for product '%s' must be greater than zero.", product_name))

            product = self._ai_find_sale_product(product_name)
            order_lines.append((0, 0, {
                "product_id": product.id,
                "product_uom_qty": quantity,
            }))
            line_summaries.append(_("- %(product)s x %(quantity)s", product=product.display_name, quantity=quantity))

        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "note": note or False,
            "order_line": order_lines,
        })
        order.message_post(body=_(
            "This draft quotation was created by the AI assistant for %(user)s.",
            user=self.env.user.display_name,
        ))

        return _(
            "Draft quotation %(order)s has been created for %(partner)s.\n%(lines)s\nPlease review prices, taxes, and delivery details before confirming it.",
            order=order.name,
            partner=partner.display_name,
            lines="\n".join(line_summaries),
        )

    def _ai_tool_add_products_to_website_cart(self, product_names, quantities, note=False):
        """Add products to the current website shopping cart."""
        website = getattr(request, "website", None) or self.env["website"].get_current_website()
        if not website:
            raise UserError(_("This tool can only be used when a website is available."))
        if not website.has_ecommerce_access():
            raise UserError(_("The current website does not allow ecommerce access."))
        if not product_names:
            raise UserError(_("Please provide at least one product to add to the cart."))
        if len(product_names) != len(quantities):
            raise UserError(_("Product names and quantities must have the same number of items."))

        self._ai_prepare_website_sale_request(website)
        prepared_lines = []
        for product_name, quantity in zip(product_names, quantities):
            product_name = (product_name or "").strip()
            if not product_name:
                raise UserError(_("Each cart line must include a product name."))
            if (
                isinstance(quantity, bool)
                or not isinstance(quantity, (int, float))
                or not isfinite(quantity)
                or quantity <= 0
                or quantity != int(quantity)
            ):
                raise UserError(_("The quantity for product '%s' must be a positive whole number.", product_name))

            product = self._ai_find_sale_product(product_name, website=website)
            prepared_lines.append((product, int(quantity)))

        original_cart = request.cart
        session_keys = ("sale_order_id", "website_sale_cart_quantity")
        original_session = {key: request.session[key] for key in session_keys if key in request.session}
        line_summaries = []
        warnings = []
        try:
            # AI catches tool errors and can retry within the same transaction.
            # Roll back the complete batch so a retry cannot add earlier lines twice.
            with self.env.cr.savepoint():
                order = original_cart or website._create_cart()
                for product, quantity in prepared_lines:
                    values = order.with_context(skip_cart_verification=True)._cart_add(
                        product_id=product.id,
                        quantity=quantity,
                    )
                    if warning := values.get("warning"):
                        warnings.append(warning)
                    line_summaries.append(_(
                        "- %(product)s x %(quantity)s",
                        product=product.display_name,
                        quantity=values.get("added_qty", 0),
                    ))
                order._verify_cart_after_update()
                if note:
                    order._message_log(body=_("AI website cart note: %s", note))
        except Exception:
            # SQL savepoints do not restore the HTTP session or request cache.
            request.cart = original_cart
            for key in session_keys:
                if key in original_session:
                    request.session[key] = original_session[key]
                else:
                    request.session.pop(key, None)
            raise

        message = _(
            "Cart update results:\n%(lines)s\nYou can open /shop/cart to review quantities and proceed to checkout.",
            lines="\n".join(line_summaries),
        )
        if warnings:
            message += _("\nWarnings:\n%s", "\n".join(warnings))
        return message

    def _ai_prepare_website_sale_request(self, website):
        if not getattr(request, "website", None):
            request.website = website
        if not getattr(request, "cart", None):
            request.cart = website._get_and_cache_current_cart()
        if not getattr(request, "fiscal_position", None):
            request.fiscal_position = website._get_and_cache_current_fiscal_position()
        if not getattr(request, "pricelist", None):
            request.pricelist = website._get_and_cache_current_pricelist()

    def _ai_tool_search_website_products(self, query):
        """Return real website catalog names and references before adding products."""
        query = (query or "").strip()
        if not query:
            raise UserError(_("Please provide a product name, reference, or a few product keywords."))
        website = getattr(request, "website", None) or self.env["website"].get_current_website()
        if not website or not website.has_ecommerce_access():
            raise UserError(_("The current website does not allow ecommerce access."))
        self._ai_prepare_website_sale_request(website)
        Product = self.env["product.product"].sudo().with_company(website.company_id).with_context(
            website_id=website.id,
        )
        domain = Domain("sale_ok", "=", True) & Domain("is_published", "=", True) & website.website_domain()
        products = Product.browse()
        has_more = False
        for lang in dict.fromkeys((self.env.lang or "en_US", "en_US")):
            LocalProduct = Product.with_context(lang=lang, display_default_code=False)
            candidates = LocalProduct.search(domain & self._ai_sale_product_keyword_domain(query), limit=101)
            has_more |= len(candidates) > 100
            candidates = candidates.filtered(lambda product: product._is_add_to_cart_allowed())
            products |= Product.browse(candidates.ids)

        # A model may send both a translated term and its English equivalent.
        # Match each keyword in either catalog language, then intersect matches.
        if not products:
            shared_ids = None
            for word in re.findall(r"\w+", query.casefold()):
                word_ids = set()
                for lang in dict.fromkeys((self.env.lang or "en_US", "en_US")):
                    candidates = Product.with_context(lang=lang).search(
                        domain & self._ai_sale_product_keyword_domain(word), limit=101,
                    )
                    has_more |= len(candidates) > 100
                    word_ids.update(candidates.ids)
                shared_ids = word_ids if shared_ids is None else shared_ids & word_ids
                if not shared_ids:
                    break
            products = Product.browse(sorted(shared_ids or ())).filtered(
                lambda product: product._is_add_to_cart_allowed(),
            )

        # Prefer a precise reference/name over broader keyword matches.
        if products:
            exact = products.filtered(lambda product: query.casefold() in {
                (product.default_code or "").casefold(),
                (product.barcode or "").casefold(),
                product.name.casefold(),
                product.with_context(lang="en_US").name.casefold(),
            })
            products = exact or products
        return {
            "products": [{
                "product_id": product.id,
                "name": product.display_name,
                "reference": product.default_code or "",
                "catalog_name": product.with_context(lang="en_US", display_default_code=False).display_name,
                "attributes": product.product_template_attribute_value_ids.mapped("name"),
            } for product in products[:10]],
            "has_more": has_more or len(products) > 10,
        }

    def _ai_find_sale_product(self, product_name, website=None):
        Product = self.env["product.product"].sudo() if website else self.env["product.product"]
        domain = Domain("sale_ok", "=", True)
        if website:
            Product = Product.with_company(website.company_id).with_context(website_id=website.id)
            domain &= Domain("is_published", "=", True) & website.website_domain()

        product = Product.search(domain & Domain("default_code", "=ilike", product_name), limit=2)
        if not product:
            product = Product.search(domain & Domain("barcode", "=", product_name), limit=2)
        if not product:
            # Shoppers and AI may use an English catalog name in another UI language.
            for lang in dict.fromkeys((self.env.lang or "en_US", "en_US")):
                LocalProduct = Product.with_context(lang=lang, display_default_code=False)
                product = LocalProduct.search(domain & Domain("name", "=ilike", product_name), limit=2)
                if not product:
                    product = self._ai_match_sale_product_variant(LocalProduct, domain, product_name)
                if not product:
                    product = LocalProduct.search(domain & Domain("display_name", "ilike", product_name), limit=6)
                if product:
                    product = Product.browse(product.ids)
                    break

        if website:
            product = product.filtered(lambda p: p._is_add_to_cart_allowed())
        if not product:
            if website:
                # Return actual variants for a recognized template when the AI
                # translated or omitted an attribute instead of inventing a match.
                suggestions = Product.browse()
                words = re.findall(r"\w+", product_name.casefold())
                for lang in dict.fromkeys((self.env.lang or "en_US", "en_US")):
                    LocalProduct = Product.with_context(lang=lang)
                    if words:
                        candidates = LocalProduct.search(domain & Domain.OR([
                            Domain("name", "ilike", word) for word in words
                        ]), limit=10)
                        suggestions |= Product.browse(candidates.filtered(
                            lambda item: item._is_add_to_cart_allowed(),
                        ).ids)
                if suggestions:
                    matches = "\n".join(
                        "- %s" % item.with_context(lang="en_US").display_name for item in suggestions[:10]
                    )
                    raise UserError(_(
                        "No exact product matches '%(product_name)s'. No products from this batch were added. "
                        "These are catalog candidates, not a confirmed match. Use the actual reference or full "
                        "variant name only when it matches the requested specifications; otherwise ask the customer.\n%(matches)s",
                        product_name=product_name,
                        matches=matches,
                    ))
            raise UserError(_("No sellable product was found for '%s'.", product_name))
        if len(product) > 1:
            matches = "\n".join("- %s" % item.display_name for item in product[:10])
            raise ValidationError(_(
                "Multiple products match '%(product_name)s'. Please ask which variant the customer wants, "
                "or use their previously specified reference. No products from this batch were added.\n%(matches)s",
                product_name=product_name,
                matches=matches,
            ))
        return product

    def _ai_match_sale_product_variant(self, Product, domain, product_name):
        """Keep all variants matching the given details, including omitted attributes."""
        candidate_domain = domain & self._ai_sale_product_keyword_domain(product_name)
        candidates = Product.search(candidate_domain, limit=101)
        if len(candidates) > 100:
            raise ValidationError(_(
                "Too many products match '%s'. Please provide an internal reference or barcode.", product_name,
            ))
        return candidates

    def _ai_sale_product_keyword_domain(self, query):
        words = re.findall(r"\w+", query.casefold())
        if not words:
            return Domain.FALSE
        return Domain.AND([
            Domain.OR([
                Domain("name", "ilike", word),
                Domain("default_code", "ilike", word),
                Domain("barcode", "ilike", word),
                Domain("product_template_attribute_value_ids.name", "ilike", word),
            ]) for word in words
        ])
