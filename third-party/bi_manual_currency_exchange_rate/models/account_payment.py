# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models,api, _,Command
from odoo.exceptions import UserError, ValidationError


class account_payment(models.TransientModel):
    _inherit = 'account.payment.register'

    manual_currency_rate_active = fields.Boolean('Apply Manual Exchange')
    manual_currency_rate = fields.Float('Rate', digits=(12, 6))

    @api.onchange('manual_currency_rate_active', 'currency_id')
    def check_currency_id(self):
        for payment in self:
            if payment.manual_currency_rate_active:
                if payment.currency_id == payment.company_id.currency_id:
                    payment.manual_currency_rate_active = False
                    raise UserError(_('Company currency and Payment currency same, You can not add manual Exchange rate for same currency.'))

    @api.model
    def default_get(self, fields_list):
        # OVERRIDE
        res = super().default_get(fields_list)
        if 'line_ids' in res:
            if self._context.get('active_model') == 'account.move':
                    lines = self.env['account.move'].browse(self._context.get('active_ids', [])).line_ids
            elif self._context.get('active_model') == 'account.move.line':
                lines = self.env['account.move.line'].browse(self._context.get('active_ids', []))
            
            if lines and self.can_edit_wizard:
                res.update({
                    'manual_currency_rate_active': lines[0].move_id.manual_currency_rate_active or False,
                    'manual_currency_rate': lines[0].move_id.manual_currency_rate
                })
        return res
    
    @api.depends('can_edit_wizard')
    def _compute_group_payment(self):
        for wizard in self:
            if wizard.can_edit_wizard:
                wizard.group_payment = len(wizard.batches[0]['lines'].move_id) == 1
                move_id = wizard.batches[0]['lines'].move_id
                if len(move_id) == 1:
                    wizard.update({'manual_currency_rate_active': move_id.manual_currency_rate_active,'manual_currency_rate':move_id.manual_currency_rate})
            else:
                wizard.group_payment = False
                wizard.update({'manual_currency_rate_active': False,'manual_currency_rate':0.0,})
    
    @api.model
    def _create_payment_vals_from_batch(self, batch_result):
        rec = super(account_payment, self)._create_payment_vals_from_batch(batch_result)
        rec.update({
            'manual_currency_rate_active': self.manual_currency_rate_active,
            'manual_currency_rate': self.manual_currency_rate
        })
        return rec

    def _get_total_amount_in_wizard_currency_to_full_reconcile(self, batch_result, early_payment_discount=True):
        """ Compute the total amount needed in the currency of the wizard to fully reconcile the batch of journal
        items passed as parameter.

        :param batch_result:    A batch returned by '_get_batches'.
        :return:                An amount in the currency of the wizard.
        """
        self.ensure_one()
        is_inverted_rate = self.env['ir.config_parameter'].sudo().get_param("bi_manual_currency_exchange_rate.inverted_rate")
        comp_curr = self.company_id.currency_id
        if self.source_currency_id == self.currency_id:
            # Same currency (manage the early payment discount).
            return self._get_total_amount_using_same_currency(batch_result, early_payment_discount=early_payment_discount)
        elif self.source_currency_id != comp_curr and self.currency_id == comp_curr:
            # Foreign currency on source line but the company currency one on the opposite line.
            if is_inverted_rate and self.manual_currency_rate_active:
                return (self.source_amount_currency * self.manual_currency_rate or 0.0, True)
            elif not is_inverted_rate and self.manual_currency_rate_active:
                return (self.source_amount_currency / self.manual_currency_rate or 0.0,True)
            else:
                return self.source_currency_id._convert(
                    self.source_amount_currency,
                    comp_curr,
                    self.company_id,
                    self.payment_date,
                ), False
        elif self.source_currency_id == comp_curr and self.currency_id != comp_curr:
            # Company currency on source line but a foreign currency one on the opposite line.
            residual_amount = 0.0
            for aml in batch_result['lines']:
                if not aml.move_id.payment_id and not aml.move_id.statement_line_id:
                    conversion_date = self.payment_date
                else:
                    conversion_date = aml.date
                    
                if is_inverted_rate and self.manual_currency_rate_active:
                    residual_amount += (aml.amount_residual * self.manual_currency_rate or 0.0)
                elif not is_inverted_rate and self.manual_currency_rate_active:
                    residual_amount += (aml.amount_residual / self.manual_currency_rate or 0.0)
                else:
                    residual_amount += comp_curr._convert(
                    aml.amount_residual,
                    self.currency_id,
                    self.company_id,
                    conversion_date,
                )
            return abs(residual_amount), False
        else:
            # Foreign currency on payment different than the one set on the journal entries.
            if is_inverted_rate and self.manual_currency_rate:
                return (self.source_amount * self.manual_currency_rate or 0.0, True)
            elif not is_inverted_rate and self.manual_currency_rate:
                return (self.source_amount / self.manual_currency_rate or 0.0, True)
            else:
                return comp_curr._convert(
                    self.source_amount,
                    self.currency_id,
                    self.company_id,
                    self.payment_date,
                ), False

    def _create_payment_vals_from_wizard(self,batch_result):
        res = super(account_payment, self)._create_payment_vals_from_wizard(batch_result)
        if self.manual_currency_rate_active:
            res.update({'manual_currency_rate_active': self.manual_currency_rate_active, 'manual_currency_rate': self.manual_currency_rate,'check_active_currency':True})
        else: 
            res.update({'manual_currency_rate_active': False, 'manual_currency_rate': 0.0,'check_active_currency':False})
        return res

class AccountPayment(models.Model):
    _inherit = "account.payment"
    _description = "Payments"

    manual_currency_rate_active = fields.Boolean('Apply Manual Exchange')
    manual_currency_rate = fields.Float('Rate', digits=(12, 6))
    amount_currency = fields.Float('Amount Currency')
    check_active_currency = fields.Boolean('Check Active Currency')

    @api.onchange('manual_currency_rate_active', 'currency_id')
    def check_currency_id(self):
        for payment in self:
            if payment.manual_currency_rate_active:
                if payment.currency_id == payment.company_id.currency_id:
                    payment.manual_currency_rate_active = False
                    raise UserError(_('Company currency and Payment currency same, You can not add manual Exchange rate for same currency.'))

    @api.model
    def default_get(self, default_fields):
        rec = super(AccountPayment, self).default_get(default_fields)
        active_ids = self._context.get('active_ids') or self._context.get('active_id')
        active_model = self._context.get('active_model')

        # Check for selected invoices ids
        if not active_ids or active_model != 'account.move':
            return rec

        invoices = self.env['account.move'].browse(active_ids).filtered(
            lambda move: move.is_invoice(include_receipts=True))

        if (len(invoices) == 1):
            rec.update({
                'manual_currency_rate_active': invoices.manual_currency_rate_active,
                'manual_currency_rate': invoices.manual_currency_rate,
            })
        return rec

    @api.model
    def _compute_payment_amount(self, invoices, currency, journal, date):
        '''Compute the total amount for the payment wizard.
        :param invoices:    Invoices on which compute the total as an account.invoice recordset.
        :param currency:    The payment's currency as a res.currency record.
        :param journal:  The payment's journal as an account.journal record.
        :param date:        The payment's date as a datetime.date object.
        :return:            The total amount to pay the invoices.
        '''
        company = journal.company_id
        currency = currency or journal.currency_id or company.currency_id
        date = date or fields.Date.today()

        if not invoices:
            return 0.0

        self.env['account.move'].flush(['type', 'currency_id'])
        self.env['account.move.line'].flush(['amount_residual', 'amount_residual_currency', 'move_id', 'account_id'])
        self.env['account.account'].flush(['user_type_id'])
        self.env['account.account.type'].flush(['type'])
        self._cr.execute('''
                SELECT
                    move.type AS type,
                    move.currency_id AS currency_id,
                    SUM(line.amount_residual) AS amount_residual,
                    SUM(line.amount_residual_currency) AS residual_currency
                FROM account_move move
                LEFT JOIN account_move_line line ON line.move_id = move.id
                LEFT JOIN account_account account ON account.id = line.account_id
                LEFT JOIN account_account_type account_type ON account_type.id = account.user_type_id
                WHERE move.id IN %s
                AND account_type.type IN ('receivable', 'payable')
                GROUP BY _prepare_move_line_default_valsmove.id, move.type
            ''', [tuple(invoices.ids)])
        query_res = self._cr.dictfetchall()

        total = 0.0
        for inv in invoices:
            for res in query_res:
                move_currency = self.env['res.currency'].browse(res['currency_id'])
                if move_currency == currency and move_currency != company.currency_id:
                    total += res['residual_currency']
                else:
                    if not inv.manual_currency_rate_active:
                        total += company.currency_id._convert(res['amount_residual'], currency, company, date)
                    else:
                        total += res['residual_currency'] * inv.manual_currency_rate
        return total

    @api.depends('invoice_ids', 'amount', 'payment_date', 'currency_id', 'payment_type', 'manual_currency_rate')
    def _compute_payment_difference(self):
        draft_payments = self.filtered(lambda p: p.invoice_ids and p.state == 'draft')
        for pay in draft_payments:
            payment_amount = -pay.amount if pay.payment_type == 'outbound' else pay.amount
            pay.payment_difference = pay._compute_payment_amount(pay.invoice_ids, pay.currency_id, pay.journal_id,
                                                                 pay.payment_date) - payment_amount
        (self - draft_payments).payment_difference = 0

    def _prepare_move_line_default_vals(self, write_off_line_vals=None,force_balance=None):
        result = super()._prepare_move_line_default_vals(write_off_line_vals,force_balance)
        if self.manual_currency_rate_active and self.manual_currency_rate > 0:
            for res in result:
                if self.company_id.currency_id.id == self.currency_id.id:
                    amount_currency = res['amount_currency']
                    is_inverted_rate = self.env['ir.config_parameter'].sudo().get_param("bi_manual_currency_exchange_rate.inverted_rate")
                    if is_inverted_rate:
                        if res.get('debit'):
                            res['amount_currency'] = amount_currency * self.manual_currency_rate
                            res['debit'] = abs(amount_currency) * self.manual_currency_rate
                        else:
                            res['balance'] = res['amount_currency'] * self.manual_currency_rate
                        if res.get('credit'):
                            res['amount_currency'] = amount_currency * self.manual_currency_rate
                            res['credit'] =  abs(amount_currency) * self.manual_currency_rate
                        else:
                            res['balance'] = res['amount_currency'] * self.manual_currency_rate
                    else:
                        if res.get('debit'):
                            res['amount_currency'] = amount_currency / self.manual_currency_rate
                            res['debit'] = abs(amount_currency) / self.manual_currency_rate
                        else:
                            res['balance'] = res['amount_currency'] / self.manual_currency_rate
                        if res.get('credit'):
                            res['amount_currency'] = amount_currency / self.manual_currency_rate
                            res['credit'] =  abs(amount_currency) / self.manual_currency_rate
                        else:
                            res['balance'] = res['amount_currency'] / self.manual_currency_rate
                else:
                    amount_currency = res['amount_currency']
                    is_inverted_rate = self.env['ir.config_parameter'].sudo().get_param("bi_manual_currency_exchange_rate.inverted_rate")
                    if is_inverted_rate:
                        if res.get('debit') and res.get('debit') > 0:
                            res['amount_currency'] = amount_currency 
                            res['debit'] = abs(amount_currency) * self.manual_currency_rate
                        else:
                            res['balance'] = res['amount_currency'] * self.manual_currency_rate
                        if res.get('credit') and res.get('credit') > 0:
                            res['amount_currency'] = amount_currency 
                            res['credit'] = abs(amount_currency) * self.manual_currency_rate
                        else:
                            res['balance'] = res['amount_currency'] * self.manual_currency_rate
                    else:
                        if res.get('debit') and res.get('debit') > 0:
                            res['amount_currency'] = amount_currency 
                            res['debit'] = abs(amount_currency) / self.manual_currency_rate
                        else:
                            res['balance'] = res['amount_currency'] / self.manual_currency_rate
                        if res.get('credit') and  res.get('credit') > 0:
                            res['amount_currency'] = amount_currency 
                            res['credit'] = abs(amount_currency) / self.manual_currency_rate
                        else:
                            res['balance'] = res['amount_currency'] / self.manual_currency_rate
        return result
    
    def write(self,vals):
        result = super().write(vals)
        if vals.get('amount') and vals.get('amount_currency'):
            for record in self:
                record.amount_currency = vals.get('amount')
        return result
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('amount_currency'):
                vals.update({'amount':vals.get('amount_currency')})
            result = super().create(vals_list)
            if vals.get('amount'):
                vals.update({'amount_currency':vals.get('amount')})
                result.sync_amount()
            return result

    @api.onchange('amount_currency')
    def onchange_amount_currency(self):
        for record in self:
            record.amount = record.amount_currency

    def _generate_journal_entry(self, write_off_line_vals=None, force_balance=None, line_ids=None):
        need_move = self.filtered(lambda p: not p.move_id and p.outstanding_account_id)
        assert len(self) == 1 or (not write_off_line_vals and not force_balance and not line_ids)

        move_vals = []
        for pay in need_move:
            move_vals.append({
                'move_type': 'entry',
                'ref': pay.memo,
                'date': pay.date,
                'journal_id': pay.journal_id.id,
                'company_id': pay.company_id.id,
                'partner_id': pay.partner_id.id,
                'currency_id': pay.currency_id.id,
                'partner_bank_id': pay.partner_bank_id.id,
                'manual_currency_rate_active' : pay.manual_currency_rate_active or False,
                'manual_currency_rate' : pay.manual_currency_rate or 0.0,
                'line_ids': line_ids or [
                    Command.create(line_vals)
                    for line_vals in pay._prepare_move_line_default_vals(
                        write_off_line_vals=write_off_line_vals,
                        force_balance=force_balance,
                    )
                ],
                'origin_payment_id': pay.id,
            })
        moves = self.env['account.move'].create(move_vals)
        for pay, move in zip(need_move, moves):
            pay.write({'move_id': move.id, 'state': 'in_process'})

    def sync_amount(self):
        for record in self:
            if record.manual_currency_rate_active and record.manual_currency_rate:
                if record.company_id.currency_id.id == record.currency_id.id:
                    if record.check_active_currency == True : 
                       record.amount_currency = record.amount 
                else:
                    record.amount_currency = record.amount
            else:
                record.amount_currency = record.amount