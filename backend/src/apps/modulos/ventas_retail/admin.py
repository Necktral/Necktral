from django.contrib import admin

from .models import (
    RetailBranchConfig,
    RetailCommandExecution,
    RetailHold,
    RetailPaymentRecord,
    RetailReturn,
    RetailSale,
    RetailTerminal,
    RetailTicket,
    RetailTicketLine,
)

admin.site.register(RetailBranchConfig)
admin.site.register(RetailTerminal)
admin.site.register(RetailTicket)
admin.site.register(RetailTicketLine)
admin.site.register(RetailPaymentRecord)
admin.site.register(RetailSale)
admin.site.register(RetailHold)
admin.site.register(RetailReturn)
admin.site.register(RetailCommandExecution)
