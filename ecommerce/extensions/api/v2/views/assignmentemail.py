"""API endpoint for sending assignment email to a user."""
import logging
from smtplib import SMTPException

from django.apps import apps
from django.core import mail
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ecommerce.extensions.api.exceptions import BadRequestException

logger = logging.getLogger(__name__)

class AssignmentEmail(APIView):
    """Sends assignment email to a user."""
    permission_classes = (IsAuthenticated,)

    REQUIRED_PARAM_EMAIL = 'user_email'
    REQUIRED_PARAM_ENTERPRISE_NAME = 'enterprise_name'
    REQUIRED_PARAM_CODE = 'code'
    REQUIRED_PARAM_ENROLLMENT_URL = 'enrollment_url'

    MISSING_REQUIRED_PARAMS_MSG = "Some required parameter(s) missing: {}"

    def get_request_value(request, key, default=None):
        """
        Get the value in the request, either through query parameters or posted data, from a key.
        """
        return request.data.get(key, request.query_params.get(key, default))

    def get_required_query_params(self, request):
        """
        Gets ``user_email``, ``enterprise_name``, ``enrollment_url`` and ``code``,
        which are the relevant parameters for this API endpoint.

        :param request: The request to this endpoint.
        :return: The ``user_email``, ``enterprise_name``, ``enrollment_url`` and ``code`` from the request.
        """
        user_email = self.get_request_value(request, self.REQUIRED_PARAM_EMAIL, '')
        enterprise_name = self.get_request_value(request, self.REQUIRED_PARAM_ENTERPRISE_NAME, '')
        code = self.get_request_value(request, self.REQUIRED_PARAM_CODE, '')
        enrollment_url = self.get_request_value(request, self.REQUIRED_PARAM_ENROLLMENT_URL, '')
        if not (user_email and enterprise_name and code and enrollment_url):
            raise BadRequestException(
                self.get_missing_params_message([
                    (self.REQUIRED_PARAM_EMAIL, bool(user_email)),
                    (self.REQUIRED_PARAM_ENTERPRISE_NAME, bool(enterprise_name)),
                    (self.REQUIRED_PARAM_CODE, bool(code)),
                    (self.REQUIRED_PARAM_ENROLLMENT_URL, bool(enrollment_url)),
                ])
            )
        return user_email, enterprise_name, code, enrollment_url

    def get_missing_params_message(self, parameter_state):
        """
        Get a user-friendly message indicating a missing parameter for the API endpoint.
        """
        params = ', '.join(name for name, present in parameter_state if not present)
        return self.MISSING_REQUIRED_PARAMS_MSG.format(params)

    def post(self, request):
        """
        POST /enterprise/api/v1/request_codes

        Requires a JSON object of the following format:
        >>> {
        >>>     "user_email": "bob@alice.com",
        >>>     "enterprise_name": "IBM",
        >>>     "code": "LEWHBGDYT",
        >>>     "enrollment_url": "http://tempurl.url/enroll"
        >>> }

        Keys:
        *email*
            Email of the customer who has requested more codes.
        *enterprise_name*
            The name of the enterprise requesting more codes.
        *code*
            Code for the user.
        *enrollment_url*
            URL for the user.
        """
        logger.info("%s", request.data)
        try:
            user_email, enterprise_name, code, enrollment_url = self.get_required_query_params(request)
        except BadRequestException as invalid_request:
            return Response({'error': str(invalid_request)}, status=status.HTTP_400_BAD_REQUEST)

        subject_line = _('Code Assignment - Code assigned by {token_enterprise_name}').format(
            token_enterprise_name=enterprise_name
        )
        body_msg = _('{token_enterprise_name} has assigned the {token_code} '
                           'code to you. Please use the following URL to enroll.\n'
                           '{token_url}').format(
            token_enterprise_name=enterprise_name,
            token_code=code,
            token_url=enrollment_url)

        app_config = apps.get_app_config("ecommerce")
        from_email_address = app_config.customer_success_email
        data = {
            self.REQUIRED_PARAM_EMAIL: email,
            self.REQUIRED_PARAM_ENTERPRISE_NAME: enterprise_name,
            self.REQUIRED_PARAM_CODE: code,
            self.REQUIRED_PARAM_ENROLLMENT_URL: enrollment_url,
        }
        try:
            mail.send_mail(
                subject_line,
                body_msg,
                from_email_address,
                [user_email],
                fail_silently=False
            )
            return Response(data, status=status.HTTP_200_OK)
        except SMTPException:
            error_message = _('[Ecommerce API] Failure in sending e-mail to {token_email} for {token_code}'
                              ' from {token_enterprise_name}').format(
                token_email=user_email,
                token_code=code,
                token_enterprise_name=enterprise_name
            )
            logger.error(error_message)
            return Response(
                {'error': str('Assignment code email could not be sent')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
