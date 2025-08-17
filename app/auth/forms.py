from flask_wtf import FlaskForm
from datetime import datetime
from wtforms import (
    StringField, 
    PasswordField, 
    BooleanField, 
    SubmitField, 
    SelectField,
    TextAreaField,
    DecimalField,
    IntegerField,
    TimeField
)
from wtforms.validators import (
    DataRequired, 
    InputRequired, 
    Length, 
    Email, 
    EqualTo, 
    ValidationError,
    NumberRange,
    Optional
)
from app.models import User, Table
from datetime import time

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class UserEditForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    role = SelectField('Role', choices=[
        ('employee', 'Employee'),
        ('manager', 'Manager'),
        ('system_control', 'System Control')
    ])
    is_admin = BooleanField('Admin')
    active = BooleanField('Active')
    password = PasswordField('New Password (admin can set directly)')
    submit = SubmitField('Update')

class UserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    role = SelectField('Role', choices=[
        ('employee', 'Employee'),
        ('manager', 'Manager'),
        ('system_control', 'System Control')
    ])
    is_admin = BooleanField('Admin')
    submit = SubmitField('Create')

    def validate_username(self, field):
        user = User.query.filter_by(username=field.data).first()
        if user:
            raise ValidationError('This username is already taken.')

class OrderForm(FlaskForm):
    table_id = SelectField('Table', coerce=int, validators=[DataRequired()])
    client_id = SelectField('Client (optional)', coerce=int, choices=[])
    notes = TextAreaField('Special Instructions')
    submit = SubmitField('Create Order')

class OrderItemForm(FlaskForm):
    product_id = SelectField('Product', coerce=int, validators=[DataRequired()])
    quantity = DecimalField('Quantity', validators=[DataRequired(), NumberRange(min=0.01)])
    special_instructions = TextAreaField('Special Instructions')
    submit = SubmitField('Add Item')

class EditUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('New Password (leave blank to keep current)', validators=[
        Length(min=8),
        EqualTo('confirm_password', message='Passwords must match')
    ])
    confirm_password = PasswordField('Confirm New Password')
    role = SelectField('Role', choices=[
        ('system_control', 'System Control'),
        ('manager', 'Manager'),
        ('employee', 'Employee')
    ], validators=[DataRequired()])
    is_admin = BooleanField('Is Admin')
    active = BooleanField('Active')
    
    def validate_username(self, field):
        if field.data != self.original_username:
            if User.query.filter_by(username=field.data).first():
                raise ValidationError('Username already in use')
    
    def __init__(self, *args, **kwargs):
        super(EditUserForm, self).__init__(*args, **kwargs)
        self.original_username = kwargs.get('obj').username if kwargs.get('obj') else None

class TableForm(FlaskForm):
    number = IntegerField('Table Number', validators=[DataRequired()])
    capacity = IntegerField('Capacity', validators=[DataRequired(), NumberRange(min=1)])
    location = SelectField(
        'Location',
        choices=[
            ('', 'Select location'),
            ('Indoor Section', 'Indoor Section'),
            ('Outdoor Section', 'Outdoor Section'),
            ('VIP / Lounge Area', 'VIP / Lounge Area'),
            ('Bar Counter', 'Bar Counter')
        ]
    )
    submit = SubmitField('Save Table')

    def validate_number(self, field):
        if Table.query.filter_by(number=field.data).first():
            raise ValidationError('This table number already exists.')


class ShiftForm(FlaskForm):
    shift_type = SelectField(
        'Shift Type',
        choices=[
            ('custom', 'Custom Shift'),
            ('morning', 'Morning Shift (7:00 AM - 5:00 PM)'),
            ('evening', 'Evening Shift (5:00 PM - 12:00 AM)')
        ],
        default='custom',
        validators=[DataRequired()]
    )
    
    name = StringField(
        'Shift Name', 
        validators=[DataRequired()],
        render_kw={"placeholder": "e.g. Morning Shift"}
    )
    
    start_hour = SelectField(
        'Start Hour', 
        choices=[(str(i).zfill(2), str(i).zfill(2)) for i in range(1, 13)], 
        validators=[DataRequired()]
    )
    start_minute = SelectField(
        'Start Minute', 
        choices=[(str(i).zfill(2), str(i).zfill(2)) for i in range(0, 60, 15)], 
        validators=[DataRequired()],
        default='00'
    )
    start_ampm = SelectField(
        'AM/PM', 
        choices=[('AM', 'AM'), ('PM', 'PM')], 
        validators=[DataRequired()]
    )
    
    end_hour = SelectField(
        'End Hour', 
        choices=[(str(i).zfill(2), str(i).zfill(2)) for i in range(1, 13)], 
        validators=[DataRequired()]
    )
    end_minute = SelectField(
        'End Minute', 
        choices=[(str(i).zfill(2), str(i).zfill(2)) for i in range(0, 60, 15)], 
        validators=[DataRequired()],
        default='00'
    )
    end_ampm = SelectField(
        'AM/PM', 
        choices=[('AM', 'AM'), ('PM', 'PM')], 
        validators=[DataRequired()]
    )
    
    description = TextAreaField('Description', validators=[Optional()])
    grace_period = IntegerField(
        'Grace Period (minutes)', 
        validators=[Optional(), NumberRange(min=0)],
        default=15
    )
    is_active = BooleanField('Is Active', default=True)
    submit = SubmitField('Save Shift')

    def validate(self, extra_validators=None):
        # First call the parent's validate method
        if not super().validate():
            return False

        # Skip time validation if using predefined shifts
        if self.shift_type.data in ['morning', 'evening']:
            return True

        # Convert times to 24-hour format for comparison (custom shifts only)
        try:
            start_time_str = f"{self.start_hour.data}:{self.start_minute.data} {self.start_ampm.data}"
            end_time_str = f"{self.end_hour.data}:{self.end_minute.data} {self.end_ampm.data}"
            
            start_time = datetime.strptime(start_time_str, '%I:%M %p').time()
            end_time = datetime.strptime(end_time_str, '%I:%M %p').time()

            if end_time <= start_time:
                self.end_ampm.errors.append('End time must be after start time')
                return False

        except ValueError:
            self.start_hour.errors.append('Invalid time combination')
            return False

        return True

    def __init__(self, *args, **kwargs):
        super(ShiftForm, self).__init__(*args, **kwargs)
        
        # Set default values for predefined shifts if selected
        if self.shift_type.data == 'morning':
            self.start_hour.data = '07'
            self.start_minute.data = '00'
            self.start_ampm.data = 'AM'
            self.end_hour.data = '05'
            self.end_minute.data = '00'
            self.end_ampm.data = 'PM'
            if not self.name.data or self.name.data == 'Custom Shift':
                self.name.data = 'Morning Shift'
                
        elif self.shift_type.data == 'evening':
            self.start_hour.data = '05'
            self.start_minute.data = '00'
            self.start_ampm.data = 'PM'
            self.end_hour.data = '12'
            self.end_minute.data = '00'
            self.end_ampm.data = 'AM'
            if not self.name.data or self.name.data == 'Custom Shift':
                self.name.data = 'Evening Shift'
class WaiterForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    phone_number = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    email = StringField('Email', validators=[Optional(), Email()])
    is_active = BooleanField('Active', default=True)
    submit = SubmitField('Register Waiter')