import smtplib
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, Blueprint, render_template, request, jsonify
from flask_login import current_user, login_required
from app.extensions import db
from datetime import datetime, timedelta
import logging
from string import Template
from urllib.parse import quote

bp = Blueprint('notifications', __name__, url_prefix='/notifications')

# Attempt to import models
try:
    from app.models import NotificationLog, Requisition, Product
    NOTIFICATION_LOGGING_ENABLED = True
except ImportError as e:
    NOTIFICATION_LOGGING_ENABLED = False
    if current_app:
        current_app.logger.warning(f"Model import error - notification logging disabled: {str(e)}")

class EmailNotifier:
    def __init__(self, app_context=None):
        self.enabled = True
        self.logger = logging.getLogger(__name__)
        self.logging_enabled = NOTIFICATION_LOGGING_ENABLED
        self.app_context = app_context or current_app.app_context()

        # Email credentials (use App Password if using Gmail)
        self.sender_email = 'janon3030@gmail.com'
        self.sender_password = 'bflu atpq mrhe wzvw'  # Make sure this is a valid Gmail App Password
        self.default_recipient = 'djanonelhard@gmail.com'

        # SMTP settings
        self.smtp_server = 'smtp.gmail.com'
        self.smtp_port = 587

    def send_email(self, recipient, subject, body):
        """Send email and log results"""
        if not self.enabled:
            self.logger.warning("Email notifications are disabled.")
            return False

        if not recipient:
            recipient = self.default_recipient

        try:
            # DNS resolution check (debugging)
            try:
                ip = socket.gethostbyname(self.smtp_server)
                self.logger.info(f"SMTP Server resolved to IP: {ip}")
            except Exception as dns_error:
                self.logger.error(f"DNS resolution failed: {str(dns_error)}")
                self._log_notification('EMAIL', recipient, body, 'FAILED', f'DNS Error: {str(dns_error)}')
                return False

            message = MIMEMultipart()
            message['From'] = self.sender_email
            message['To'] = recipient
            message['Subject'] = subject
            message.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(message)

            self._log_notification('EMAIL', recipient, body, 'SENT')
            return True

        except Exception as e:
            self.logger.error(f"Failed to send email: {str(e)}")
            self._log_notification('EMAIL', recipient, body, 'FAILED', str(e))
            return False

    def notify_low_stock(self, product_id):
        if not self.enabled:
            return False

        try:
            product = Product.query.get(product_id)
            if not product:
                self.logger.error(f"Product {product_id} not found.")
                return False

            subject = f"Low Stock Alert: {product.name}"
            body = (
                f"Product: {product.name}\n"
                f"Current Stock: {product.current_stock}\n"
                f"Minimum Stock: {product.min_stock}\n\n"
                f"Please replenish inventory as soon as possible."
            )

            return self.send_email(self.default_recipient, subject, body)
        except Exception as e:
            self.logger.error(f"Low stock notification failed: {str(e)}")
            return False

    def notify_new_requisition(self, requisition_id):
        if not self.enabled:
            return False

        try:
            requisition = Requisition.query.get(requisition_id)
            if not requisition:
                self.logger.error(f"Requisition {requisition_id} not found.")
                return False

            subject = f"New Requisition Created: #{requisition.id}"
            # Get username and product name if available
            username = requisition.requester.name if hasattr(requisition, 'requester') and requisition.requester else str(requisition.user_id)
            product_name = requisition.product.name if hasattr(requisition, 'product') and requisition.product else 'N/A'
            body = (
                f"New requisition has been created:\n\n"
                f"Requisition ID: {requisition.id}\n"
                f"Product: {product_name}\n"
                f"Created by: {username} (User ID: {requisition.user_id})\n"
                f"Quantity requested: {requisition.requested_qty}\n"
                f"Current Quantity available: {requisition.current_stock}\n"
                f"Date: {requisition.date.strftime('%Y-%m-%d %H:%M')}\n"
                f"Please review and process this requisition."
            )

            return self.send_email(self.default_recipient, subject, body)
        except Exception as e:
            self.logger.error(f"New requisition notification failed: {str(e)}")
            return False

    def _log_notification(self, notification_type, recipient, content, status, error_message=None):
        if not self.logging_enabled:
            return

        try:
            log = NotificationLog(
                notification_type=notification_type,
                recipient=recipient,
                content=content,
                status=status,
                error_message=error_message,
                timestamp=datetime.utcnow()
            )
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            self.logger.error(f"Failed to log notification: {str(e)}")

def check_low_stock_products():
    """Check and notify low-stock products"""
    if not current_app.config.get('EMAIL_NOTIFICATIONS_ENABLED', True):
        return 0

    notification_threshold = timedelta(hours=current_app.config.get('NOTIFICATION_COOLDOWN_HOURS', 24))
    notifier = EmailNotifier()
    notified_count = 0

    with current_app.app_context():
        try:
            query = Product.query.filter(Product.current_stock <= Product.min_stock)

            if hasattr(Product, 'last_notified_at'):
                query = query.filter(
                    (Product.last_notified_at == None) |
                    (Product.last_notified_at < datetime.utcnow() - notification_threshold)
                )
            elif NOTIFICATION_LOGGING_ENABLED:
                notified_ids = [
                    log.content.split('Product: ')[1].split('\n')[0]
                    for log in NotificationLog.query.filter(
                        NotificationLog.notification_type == 'EMAIL',
                        NotificationLog.status == 'SENT',
                        NotificationLog.timestamp >= datetime.utcnow() - notification_threshold
                    ).all()
                    if 'Product: ' in log.content
                ]
                query = query.filter(~Product.name.in_(notified_ids))

            for product in query.all():
                if notifier.notify_low_stock(product.id):
                    notified_count += 1
                    if hasattr(product, 'last_notified_at'):
                        product.last_notified_at = datetime.utcnow()
                        db.session.commit()

            return notified_count
        except Exception as e:
            current_app.logger.error(f"Low stock check failed: {str(e)}")
            return 0

@bp.route('/')
@login_required
def index():
    """Notification dashboard"""
    recent_logs = []
    if NOTIFICATION_LOGGING_ENABLED:
        recent_logs = NotificationLog.query.order_by(
            NotificationLog.timestamp.desc()
        ).limit(10).all()

    return render_template(
        'notifications/dashboard.html',
        logs=recent_logs,
        email_enabled=current_app.config.get('EMAIL_NOTIFICATIONS_ENABLED', True),
        logging_enabled=NOTIFICATION_LOGGING_ENABLED
    )

@bp.route('/test-notification', methods=['POST'])
@login_required
def test_notification():
    """Send test email to check configuration"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        notifier = EmailNotifier()
        if not notifier.enabled:
            return jsonify({'success': False, 'message': 'Email notifications are disabled'}), 400

        message = (
            f"🔔 Test Notification 🔔\n\n"
            f"This is a test message from {current_app.config.get('APP_NAME', 'Our System')}.\n"
            f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"System Status: Operational ✅"
        )

        result = notifier.send_email(
            current_app.config.get('ADMIN_EMAIL', notifier.default_recipient),
            "Test Notification",
            message
        )

        if result:
            return jsonify({'success': True, 'message': 'Test notification sent'})
        return jsonify({'success': False, 'message': 'Failed to send notification'}), 500

    except Exception as e:
        current_app.logger.error(f"Test notification failed: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/email-status')
@login_required
def email_status():
    """Returns current email configuration and status"""
    notifier = EmailNotifier()
    return jsonify({
        'enabled': notifier.enabled,
        'sender_email': notifier.sender_email,
        'default_recipient': notifier.default_recipient,
        'smtp_server': notifier.smtp_server,
        'smtp_port': notifier.smtp_port
    })
