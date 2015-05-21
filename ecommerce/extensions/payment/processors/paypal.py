from decimal import Decimal
import logging
from urlparse import urljoin

from django.conf import settings
from django.core.urlresolvers import reverse
from oscar.apps.payment.exceptions import GatewayError
from oscar.core.loading import get_model
import paypalrestsdk

from ecommerce.extensions.order.constants import PaymentEventTypeName
from ecommerce.extensions.payment.processors import BasePaymentProcessor

logger = logging.getLogger(__name__)

PaymentEvent = get_model('order', 'PaymentEvent')
PaymentEventType = get_model('order', 'PaymentEventType')
PaymentProcessorResponse = get_model('payment', 'PaymentProcessorResponse')
Source = get_model('payment', 'Source')
SourceType = get_model('payment', 'SourceType')


class Paypal(BasePaymentProcessor):
    """
    PayPal REST API (May 2015)

    For reference, see https://developer.paypal.com/docs/api/.
    """
    NAME = u'paypal'

    def __init__(self):
        """
        Constructs a new instance of the PayPal processor.

        Raises:
            KeyError: If a required setting is not configured for this payment processor
            AttributeError: If ECOMMERCE_URL_ROOT setting is not set.
        """
        configuration = self.configuration
        self.receipt_url = configuration['receipt_url']
        self.cancel_url = configuration['cancel_url']

        self.ecommerce_url_root = settings.ECOMMERCE_URL_ROOT

    def get_transaction_parameters(self, basket, request=None):
        """
        Create a new PayPal payment.

        Arguments:
            basket (Basket): The basket of products being purchased.

        Keyword Arguments:
            request (Request): A Request object which is used to construct PayPal's `return_url`.

        Returns:
            dict: PayPal-specific parameters required to complete a transaction. Must contain a URL
                to which users can be directed in order to approve a newly created payment.

        Raises:
            GatewayError: Indicates a general error or unexpected behavior on the part of PayPal which prevented
                a payment from being created.
        """
        return_url = urljoin(self.ecommerce_url_root, reverse('paypal_execute'))
        data = {
            'intent': 'sale',
            'redirect_urls': {
                'return_url': return_url,
                'cancel_url': self.cancel_url,
            },
            'payer': {
                'payment_method': 'paypal',
            },
            'transactions': [{
                'amount': {
                    'total': unicode(basket.total_incl_tax),
                    'currency': basket.currency,
                },
                'item_list': {
                    'items': [
                        {
                            'quantity': line.quantity,
                            'name': line.product.title,
                            'price': unicode(line.price_incl_tax),
                            'currency': line.stockrecord.price_currency,
                        }
                        for line in basket.all_lines()
                    ],
                },
                'invoice_number': unicode(basket.id),
            }],
        }

        payment = paypalrestsdk.Payment(data)
        payment.create()

        # Raise an exception for payments that were not successfully created. Consuming code is
        # responsible for handling the exception.
        if not payment.success():
            error = self._get_error(payment)
            entry = self.record_processor_response(error, transaction_id=error['debug_id'], basket=basket)

            logger.error(
                u"Failed to create PayPal payment for basket [%d]. PayPal's response was recorded in entry [%d].",
                basket.id,
                entry.id
            )

            raise GatewayError

        entry = self.record_processor_response(payment.to_dict(), transaction_id=payment.id, basket=basket)
        logger.info(u"Successfully created PayPal payment [%s] for basket [%d].", payment.id, basket.id)

        # Dat HATEOAS
        for link in payment.links:
            if link.rel == 'approval_url':
                approval_url = link.href
                break
        else:
            logger.error(
                u"Approval URL missing from PayPal payment [%s]. PayPal's response was recorded in entry [%d].",
                payment.id,
                entry.id
            )
            raise GatewayError

        parameters = {
            'payment_page_url': approval_url,
        }

        return parameters

    def handle_processor_response(self, response, basket=None):
        """
        Execute an approved PayPal payment.

        This method creates PaymentEvents and Sources for approved payments.

        Arguments:
            response (dict): Dictionary of parameters returned by PayPal in the `return_url` query string.

        Keyword Arguments:
            basket (Basket): Basket being purchased via the payment processor.

        Raises:
            GatewayError: Indicates a general error or unexpected behavior on the part of PayPal which prevented
                an approved payment from being executed.
        """
        data = {'payer_id': response.get('PayerID')}

        payment = paypalrestsdk.Payment.find(response.get('paymentId'))
        payment.execute(data)

        # Raise an exception for payments that were not successfully executed. Consuming code is
        # responsible for handling the exception.
        if not payment.success():
            error = self._get_error(payment)
            entry = self.record_processor_response(error, transaction_id=error['debug_id'], basket=basket)

            logger.error(
                u"Failed to execute PayPal payment [%s]. PayPal's response was recorded in entry [%d].",
                payment.id,
                entry.id
            )

            raise GatewayError

        entry = self.record_processor_response(payment.to_dict(), transaction_id=payment.id, basket=basket)
        logger.info(u"Successfully executed PayPal payment [%s] for basket [%d].", payment.id, basket.id)

        # Get or create Source used to track transactions related to PayPal
        source_type, __ = SourceType.objects.get_or_create(name=self.NAME)
        currency = payment.transactions[0].amount.currency
        total = Decimal(payment.transactions[0].amount.total)
        transaction_id = payment.id
        email = payment.payer.payer_info.email

        source = Source(
            source_type=source_type,
            currency=currency,
            amount_allocated=total,
            amount_debited=total,
            reference=transaction_id,
            label=email,
            card_type=None
        )

        # Create PaymentEvent to track payment
        event_type, __ = PaymentEventType.objects.get_or_create(name=PaymentEventTypeName.PAID)
        event = PaymentEvent(event_type=event_type, amount=total, reference=transaction_id, processor_name=self.NAME)

        return source, event

    def _get_error(self, payment):
        """
        Shameful workaround for mocking the `error` attribute on instances of
        `paypalrestsdk.Payment`. The `error` attribute is created at runtime,
        but passing `create=True` to `patch()` isn't enough to mock the
        attribute in this module.
        """
        return payment.error  # pragma: no cover