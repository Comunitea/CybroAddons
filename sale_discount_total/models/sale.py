from openerp.osv import fields, osv
from openerp import api
import openerp.addons.decimal_precision as dp


class SaleOrder(osv.Model):
    _inherit = 'sale.order'

    def _amount_all_wrapper(self, cr, uid, ids, field_name, arg, context=None):
        """ Wrapper because of direct method passing as parameter for function fields """
        return self._amount_all(cr, uid, ids, field_name, arg, context=context)

    def _amount_all(self, cr, uid, ids, field_name, arg, context=None):
        cur_obj = self.pool.get('res.currency')
        res = super(SaleOrder, self)._amount_all(cr, uid, ids, field_name, arg, context)
        for order in self.browse(cr, uid, ids, context=context):
            res[order.id]['amount_discount'] = 0.0
            cur = order.pricelist_id.currency_id
            discount = 0.0
            for line in order.order_line:
                discount += (line.product_uom_qty * line.price_unit) * line.discount / 100

            res[order.id]['amount_discount'] = cur_obj.round(cr, uid, cur, discount)
        return res

    def _get_order(self, cr, uid, ids, context=None):
        result = {}
        for line in self.pool.get('sale.order.line').browse(cr, uid, ids, context=context):
            result[line.order_id.id] = True
        return result.keys()

    _columns = {
        'discount_type': fields.selection([
            ('percent', 'Percentage'),
            ('amount', 'Amount')], 'Discount type'),
        'discount_rate': fields.float('Discount Rate', digits_compute=dp.get_precision('Account'),
                                      readonly=True,
                                      states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}, ),

        'amount_discount': fields.function(_amount_all_wrapper, digits_compute=dp.get_precision('Account'), string='Discount',
                                           multi='sums', store={
                'sale.order': (lambda self, cr, uid, ids, c={}: ids, ['order_line'], 10),
                'sale.order.line': (_get_order, ['price_unit', 'tax_id', 'discount', 'product_uom_qty'], 10),
            }, help="The total discount."),
    }

    _defaults = {
        'discount_type': 'percent',
    }

    @api.multi
    def compute_discount(self, discount):
        for order in self:
            val1 = val2 = 0.0
            disc_amnt = 0.0
            for line in order.order_line:
                val1 += (line.product_uom_qty * line.price_unit)
                line.discount = discount
                val2 += self._amount_line_tax(line)
                disc_amnt += (line.product_uom_qty * line.price_unit * line.discount)/100
            total = val1 + val2 - disc_amnt
            self.currency_id = order.pricelist_id.currency_id
            self.amount_discount = round(disc_amnt)
            self.amount_tax = round(val2)
            self.amount_total = round(total)

    @api.onchange('discount_type', 'discount_rate')
    def supply_rate(self):
        for order in self:
            if order.discount_type == 'percent':
                self.compute_discount(order.discount_rate)
            else:
                total = 0.0
                for line in order.order_line:
                    total += (line.product_uom_qty * line.price_unit)
                discount = (order.discount_rate / total) * 100
                self.compute_discount(discount)

    def _prepare_invoice(self, cr, uid, order, lines, context=None):
        invoice_vals = super(SaleOrder, self)._prepare_invoice(cr, uid, order, lines, context=context)
        invoice_vals.update({
            'discount_type': order.discount_type,
            'discount_rate': order.discount_rate
        })
        return invoice_vals
