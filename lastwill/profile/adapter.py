from django.core.mail import send_mail
from django.contrib.sites.shortcuts import get_current_site
from allauth.account.adapter import DefaultAccountAdapter
from lastwill.settings import MY_WISH_URL, WAVES_URL, SWAPS_URL, EMAIL_HOST_USER, EMAIL_HOST_USER_SWAPS
from lastwill.contracts.submodels.swaps import sendEMail
from email_messages import register_subject, register_text


class SubSiteRegistrationAdapter(DefaultAccountAdapter):

    def send_confirmation_mail(self, request, emailconfirmation, signup):
        welcome_head = ''
        current_site = get_current_site(request)
        activate_url = self.get_email_confirmation_url(request, emailconfirmation)

        to_user = emailconfirmation.email_address.user
        to_email = emailconfirmation.email_address.email

        host = self.request.META['HTTP_HOST']

        if host == MY_WISH_URL or host == WAVES_URL:
            from_email = EMAIL_HOST_USER
            welcome_head = 'MyWish Platform'

            send_mail(
                register_subject,
                register_text.format(
                    subsite_name=welcome_head,
                    user_display=to_user,
                    activate_url=activate_url
                ),
                from_email,
                [to_email]
            )

        if self.request.META['HTTP_HOST'] == SWAPS_URL:
            #from_email = EMAIL_HOST_USER_SWAPS
            welcome_head = "SWAPS.NETWORK"

            sendEMail(
                register_subject,
                register_text.format(
                    subsite_name=welcome_head,
                    user_display=to_user,
                    activate_url=activate_url
                    ),
                # from_email,
                [to_email]
                )

