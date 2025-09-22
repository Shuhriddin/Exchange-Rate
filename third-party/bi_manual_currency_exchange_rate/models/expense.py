# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta
from functools import lru_cache

from odoo import api, fields, models, _,Command
from odoo.exceptions import UserError
from odoo.tools.misc import get_lang
from odoo.osv import expression
from odoo.tools import float_is_zero, float_compare, float_round


class HrExpenseSheet(models.Model):
    _inherit ='hr.expense.sheet'
    
    expense_manual_currency_rate_active = fields.Boolean('Apply Manual Exchange')
    expense_manual_currency_rate = fields.Float('Rate', digits=(12, 6))

    @api.constrains("expense_manual_currency_rate")
    def _check_sale_manual_currency_rate(self):
        for record in self:
            if record.expense_manual_currency_rate_active:
                if record.expense_manual_currency_rate == 0:
                    raise UserError(
                        _('Exchange Rate Field is required , Please fill that.'))
                is_inverted_rate = self.env['ir.config_parameter'].sudo().get_param("bi_manual_currency_exchange_rate.inverted_rate")
                if is_inverted_rate:
                    if record.expense_manual_currency_rate <1 :
                        raise UserError(_('Exchange Rate must be greater than or equal to 1 .'))
                

    @api.onchange('expense_manual_currency_rate_active', 'currency_id')
    def check_currency_id(self):
        if self.expense_manual_currency_rate_active:
            if self.currency_id == self.company_id.currency_id:
                self.expense_manual_currency_rate_active = False
                raise UserError(
                    _('Company currency and Expense currency same, You can not add manual Exchange rate for same currency.'))

    @api.depends('account_move_ids.payment_state', 'account_move_ids.amount_residual')
    def _compute_from_account_move_ids(self):
        rec=super(HrExpenseSheet, self)._compute_from_account_move_ids()

        total_residual = 0.0
        for sheet in self:
            if sheet.expense_manual_currency_rate_active:
                for move in sheet.account_move_ids:
                    if move.manual_currency_rate_active:  # Check if manual_currency_rate_active is True
                        # If manual_currency_rate_active is True, divide the amount_residual by manual_currency_rate
                        # total_residual += move['amount_residual'] / move['manual_currency_rate']
                        is_inverted_rate = self.env['ir.config_parameter'].sudo().get_param("bi_manual_currency_exchange_rate.inverted_rate")

                        if is_inverted_rate:
                            total_residual += move['amount_residual'] * move['manual_currency_rate']
                        else:
                            total_residual += move['amount_residual'] / move['manual_currency_rate']
                    else:
                        # Otherwise, just add the amount_residual as is
                        total_residual += move['amount_residual']

                # Assign the total sum to sheet.amount_residual
                sheet.amount_residual = total_residual
        return rec

    def _prepare_bills_vals(self):
        vals = super()._prepare_bills_vals()

        if 'line_ids' in vals:
            for command, _, data_dict in vals.get('line_ids'):
                if 'price_unit' in data_dict:  # Check if 'price_unit' exists in the dictionary
                    is_inverted_rate = self.env['ir.config_parameter'].sudo().get_param("bi_manual_currency_exchange_rate.inverted_rate")
                    if is_inverted_rate:
                        data_dict['price_unit'] = data_dict['price_unit'] / self.expense_manual_currency_rate if self.expense_manual_currency_rate_active else data_dict['price_unit']
                    else:
                        data_dict['price_unit'] = data_dict['price_unit'] * self.expense_manual_currency_rate if self.expense_manual_currency_rate_active else data_dict['price_unit']
            if self.expense_manual_currency_rate_active:
                vals['manual_currency_rate_active'] = self.expense_manual_currency_rate_active
                vals['manual_currency_rate'] = self.expense_manual_currency_rate
        return vals



class HrExpens(models.Model):
    _inherit ='hr.expense'

    def _prepare_payments_vals(self):
        self.ensure_one()
        if self.sheet_id.expense_manual_currency_rate_active and self.sheet_id.expense_manual_currency_rate:
            is_inverted_rate = self.env['ir.config_parameter'].sudo().get_param("bi_manual_currency_exchange_rate.inverted_rate")
            if is_inverted_rate:
                total_amount_currency = self.total_amount_currency / self.sheet_id.expense_manual_currency_rate if self.sheet_id.expense_manual_currency_rate_active else self.total_amount_currency
            else:
                total_amount_currency = self.total_amount_currency * self.sheet_id.expense_manual_currency_rate if self.sheet_id.expense_manual_currency_rate_active else self.total_amount_currency

            journal = self.sheet_id.journal_id
            payment_method_line = self.sheet_id.payment_method_line_id
            if not payment_method_line:
                raise UserError(_("You need to add a manual payment method on the journal (%s)", journal.name))

            AccountTax = self.env['account.tax']
            rate = abs(total_amount_currency / self.total_amount) if self.total_amount else 0.0
            base_line = self._prepare_base_line_for_taxes_computation(
                price_unit=total_amount_currency,
                quantity=1.0,
                account_id=self._get_base_account(),
                rate=rate,
            )
            base_lines = [base_line]
            AccountTax._add_tax_details_in_base_lines(base_lines, self.company_id)
            AccountTax._round_base_lines_tax_details(base_lines, self.company_id)
            AccountTax._add_accounting_data_in_base_lines_tax_details(base_lines, self.company_id, include_caba_tags=self.payment_mode == 'company_account')
            tax_results = AccountTax._prepare_tax_lines(base_lines, self.company_id)

            # Base line.
            move_lines = []
            for base_line, to_update in tax_results['base_lines_to_update']:
                base_move_line = {
                    'name': self._get_move_line_name(),
                    'account_id': base_line['account_id'].id,
                    'product_id': base_line['product_id'].id,
                    'analytic_distribution': base_line['analytic_distribution'],
                    'expense_id': self.id,
                    'tax_ids': [Command.set(base_line['tax_ids'].ids)],
                    'tax_tag_ids': to_update['tax_tag_ids'],
                    'amount_currency': to_update['amount_currency'],
                    'balance': to_update['balance'],
                    # 'currency_id': base_line['currency_id'].id,
                    'currency_id': self.sheet_id.currency_id.id,
                    'partner_id': self.vendor_id.id,
                    'quantity': self.quantity,
                }
                move_lines.append(base_move_line)

            # Tax lines.
            total_tax_line_balance = 0.0
            for tax_line in tax_results['tax_lines_to_add']:
                total_tax_line_balance += tax_line['balance']
                move_lines.append(tax_line)
            base_move_line['balance'] = self.total_amount - total_tax_line_balance

            # Outstanding payment line.
            move_lines.append({
                'name': self._get_move_line_name(),
                'account_id': self.sheet_id._get_expense_account_destination(),
                'balance': -self.total_amount,
                'amount_currency': self.currency_id.round(-total_amount_currency),
                'currency_id': self.sheet_id.currency_id.id,
                'partner_id': self.vendor_id.id,
            })
            payment_vals = {
                'date': self.date,
                'memo': self.name,
                'journal_id': journal.id,
                'amount': total_amount_currency,
                'payment_type': 'outbound',
                'partner_type': 'supplier',
                'partner_id': self.vendor_id.id,
                'currency_id': self.sheet_id.currency_id.id,
                'payment_method_line_id': payment_method_line.id,
                'company_id': self.company_id.id,
                'manual_currency_rate_active': self.sheet_id.expense_manual_currency_rate_active,
                'manual_currency_rate':self.sheet_id.expense_manual_currency_rate,
            }
            move_vals = {
                **self.sheet_id._prepare_move_vals(),
                'ref': self.name,
                'date': self.date,  # Overidden from self.sheet_id._prepare_move_vals() so we can use the expense date for the account move date
                'journal_id': journal.id,
                'partner_id': self.vendor_id.id,
                'currency_id': self.sheet_id.currency_id.id,
                'line_ids': [Command.create(line) for line in move_lines],
                'manual_currency_rate_active': self.sheet_id.expense_manual_currency_rate_active,
                'manual_currency_rate':self.sheet_id.expense_manual_currency_rate,
                'attachment_ids': [
                    Command.create(attachment.copy_data({'res_model': 'account.move', 'res_id': False, 'raw': attachment.raw})[0])
                    for attachment in self.message_main_attachment_id]
            }
            return move_vals, payment_vals

        else:
            res = super()._prepare_payments_vals()
            return res