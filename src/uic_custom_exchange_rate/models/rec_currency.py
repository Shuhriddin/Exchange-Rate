from odoo import models

class ResCurrency(models.Model):
    _inherit = 'res.currency'

    def _convert(self, from_amount, to_currency, company, date, round=True):
        """Agar kontekstda manual kurs bo'lsa, shuni ishlatamiz.
        self -> from_currency (manba), to_currency -> maqsad.
        """
        rate = self.env.context.get('manual_currency_rate')
        if rate:
            # Faqat kompaniya valyutasi bilan bog'liq konvertatsiyalarda qo'llaymiz
            company_cur = company.currency_id
            if to_currency == company_cur and self != company_cur:
                # Masalan: USD -> UZS (company): 100 * 12100
                amount = from_amount * rate
            elif self == company_cur and to_currency != company_cur:
                # Masalan: UZS -> USD: 1210000 / 12100
                amount = from_amount / rate
            else:
                # Ikki chet valyutasi o'rtasida (kamdan-kam) - manual kursni qo'llamaymiz
                return super()._convert(from_amount, to_currency, company, date, round=round)

            return to_currency.round(amount) if round else amount

        return super()._convert(from_amount, to_currency, company, date, round=round)
