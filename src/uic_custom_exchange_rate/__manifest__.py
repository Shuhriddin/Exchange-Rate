{
    "name": "Manual Exchange Rate",
    "version": "18.0.1.0.0",
    "depends": [
        "bi_manual_currency_exchange_rate",
        # agar third-party modul ishlatmasangiz, buni olib tashlang:
        # "bi_manual_currency_exchange_rate",
    ],
    "author": "JUFT-AGRO-OMAD",
    "category": "Sales/Accounting",
    "summary": "Apply manual exchange rate per invoice/payment",
    "data": [
        # "views/account_move_views.xml",
        "views/account_payment_register_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
