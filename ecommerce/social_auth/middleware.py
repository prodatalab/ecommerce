
import logging
import waffle
log = logging.getLogger('ISM')


ENABLE_SESSION_INSPECT = 'enable_session_inspect'


class InspectRequestSessionMiddleware(object):
    """Middleware to inspect session for different values
        and see what key and values are being created on Request.
    """

    def process_request(self, request):

        active = waffle.switch_is_active(ENABLE_SESSION_INSPECT)

        if active:
            log.info('===================================================')
            log.info("Request: Logs for Sessions/Request object")
            log.info('===================================================')

            # Ensuring that this middleware is only hit when both session and
            # user object is already populated by upper levels middlewares
            # for session and user object
            if hasattr(request, 'session') and hasattr(request, 'user'):

                _inspecting_request(request)
                _inspecting_session(request)

            else:
                log.info('No session and authentication middleware called.')


class InspectResponseSessionMiddleware(object):
    """Middleware to inspect session for different values
        and see what key and values are being created on Response.
    """

    def process_response(self, request, response):

        active = waffle.switch_is_active(ENABLE_SESSION_INSPECT)

        if active:
            log.info('====================================================')
            log.info("Response: Logs for Sessions/Request object")
            log.info('====================================================')

            # Ensuring that this middleware is only hit when both session and
            # user object is already populated by lower levels middlewares
            # for session and user object.
            if hasattr(request, 'session') and hasattr(request, 'user'):

                _inspecting_request(request)
                _inspecting_session(request)

            else:
                log.info('No session and authentication middleware called.')

        return response


def _inspecting_request(request):
    """
    Logging information from request object
    :param request:
    :return: None
    """

    log.info('-----------------Inspecting Request:-------------')
    try:
        if 'REQUEST_METHOD' and request.META['REQUEST_METHOD']:
            log.info('Request Method:' + request.META['REQUEST_METHOD'])
        if 'HTTP_REFERER' in request.META and request.META['HTTP_REFERER']:
            log.info('Referrer:' + request.META['HTTP_REFERER'])
        if 'REMOTE_USER' in request.META and request.META['REMOTE_USER']:
            log.info('Remote User:' + request.META['REMOTE_USER'])
        if 'REMOTE_HOST' in request.META and request.META['REMOTE_HOST']:
            log.info('Remote Host:' + request.META['REMOTE_HOST'])
        if 'REMOTE_ADDR' in request.META and request.META['REMOTE_ADDR']:
            log.info('Remote Addr:' + request.META['REMOTE_ADDR'])
        if 'HTTP_HOST' in request.META and request.META['HTTP_HOST']:
            log.info('Host Header:' + request.META['HTTP_HOST'])

        log.info('Request URI:' + request.get_raw_uri())

    except (KeyError, AttributeError) as e:
        log.exception("Error occurred while fetching request details: %s", e.message)


def _inspecting_session(request):
    """
    Logging information from session object
    :param request:
    :return: None
    """

    log.info('-----------------Inspecting Session:----------------')
    try:
        if request.user.is_authenticated():
            log.info("Session Type: Authenticated")
        else:
            log.info("Session Type: Unauthenticated")
        if request.user.is_authenticated():
            log.info(request.user.email)

        if request.session:
            session_key = str(request.session.session_key)
            log.info('Session object Key:' +
                     session_key[:10] + ' id:' + str(id(request.session)))

            # logging some of details of session cookie name used by django
            from django.conf import settings
            log.info('SCN:' + settings.SESSION_COOKIE_NAME)
        else:
            log.info('No Session object found')

    except (KeyError, AttributeError) as e:
        log.exception("Error occurred while fetching session details: %s", e.message)
