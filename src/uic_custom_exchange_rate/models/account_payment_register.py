# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'


    manual_currency_rate_active_uic = fields.Boolean(string="Use Manual Rate")
    manual_currency_rate_uic = fields.Float(string="Rate (SUM per 1 USD)", digits=(16, 4))
    custom_amount_uic = fields.Float(string="Amount`s")

    custom_amount_currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.ref('base.USD').id,  # default USD
    )
    #
    # use_manual_currency_rate_uic = fields.Boolean(string='Use Manual Rate')
    # if use_manual_currency_rate_uic:
    #     child_manual_currency_rate_uic = fields.Float(string='Rate (SUM per 1 USD)')

    @api.onchange('manual_currency_rate_uic')
    def change_amount_value(self):
        total_invoice_amount_usd = 0.0
        for line in self.line_ids:
            move = line.move_id
            if move and move.amount_residual and move.currency_id.name == 'USD':
                total_invoice_amount_usd += move.amount_residual

        self.custom_amount_uic = total_invoice_amount_usd  * self.manual_currency_rate_uic


    # --- yordamchi: invoicelar qoldig'i va ularning valyutasi (odatda USD) ---
    def _residual_in_invoice_currency(self):
        invs = self.env['account.move']
        if self._context.get('active_model') == 'account.move':
            invs = self.env['account.move'].browse(self._context.get('active_ids', [])).filtered(
                lambda m: m.is_invoice(include_receipts=True)
            )
        if not invs:
            return 0.0, None
        inv_cur = invs.mapped('currency_id')[:1]  # odatda bitta (USD)
        residual = sum(inv.amount_residual for inv in invs if inv.state != 'cancel')
        _logger.info("AMOUNT WORKING")
        return residual, inv_cur

    # --- asosiy: Amount ni qayta hisoblash ---
    def _recalc_amount_with_manual_rate(self):
        """
        Agar Use Manual Rate ✅ va payment valyuta ≠ invoice valyuta bo'lsa:
        amount = residual_in_invoice_currency * manual_rate
        Aks holda: amount = residual (invoice valyutasida).
        """
        for wiz in self:
            pay_cur = wiz.currency_id
            if not pay_cur:
                continue
            residual, inv_cur = wiz._residual_in_invoice_currency()
            if not inv_cur:
                continue

            if wiz.manual_currency_rate_active_uic and wiz.manual_currency_rate_uic > 0 and pay_cur != inv_cur:
                # misol: 1475 USD * 12000 (UZS per USD) = 17 700 000 UZS
                wiz.amount = residual * wiz.manual_currency_rate_uic
                _logger.info("Recalc: %s %s × %s (%s per %s) = %s %s",
                             residual, inv_cur.name,
                             wiz.manual_currency_rate_uic, pay_cur.name, inv_cur.name,
                             wiz.amount, pay_cur.name)
            else:
                # bir xil valyuta bo'lsa — qoldiqning o'zi
                wiz.amount = residual

    # --- onchange: Rate / Currency o'zgarsa darhol hisobla ---
    @api.onchange('manual_currency_rate_active_uic', 'manual_currency_rate_uic', 'currency_id', 'journal_id')
    def onchange_manual_rate(self):
        self._recalc_amount_with_manual_rate()
        _logger.info('3R')

    # --- Create Payment bosilganda ham shu kurs bilan yozish ---
    def _create_payments(self):
        ctx = dict(self._context)
        if self.manual_currency_rate_active_uic and self.manual_currency_rate_uic > 0:
            ctx['manual_currency_rate_uic'] = self.manual_currency_rate_uic
        return super(AccountPaymentRegister, self.with_context(**ctx))._create_payments()

    # Ixtiyoriy: type="object" tugmasi uchun
    def change_summu(self):
        ctx = dict(self._context)
        if self.manual_currency_rate_active_uic and self.manual_currency_rate_uic > 0:
            ctx['manual_currency_rate_uic'] = self.manual_currency_rate_uic
        return super(AccountPaymentRegister, self.with_context(**ctx)).action_create_payments()