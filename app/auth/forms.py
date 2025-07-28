from flask_wtf import FlaskForm
from wtforms import (
    StringField, 
    PasswordField, 
    BooleanField, 
    SubmitField, 
    SelectField,
    TextAreaField,
    DecimalField,
    IntegerField
)
from wtforms.validators import (
    DataRequired, 
    InputRequired, 
    Length, 
    Email, 
    EqualTo, 
    ValidationError,
    NumberRange
)
from app.models import User, Table

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
    password = PasswordField('New Password')  # Optional
    submit = SubmitField('Update')

    def __init__(self, original_username, *args, **kwargs):
        super(UserEditForm, self).__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, field):
        if field.data != self.original_username:
            user = User.query.filter_by(username=field.data).first()
            if user:
                raise ValidationError('This username is already taken.')

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
    table_id = SelectField('Table', coerce=int, validators=[DataRequired()])  # Changed from table_number
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
    location = SelectField('Location', choices=[
        ('', 'Select location'),
        ('main', 'Main Dining'),
        ('patio', 'Patio'),
        ('bar', 'Bar Area'),
        ('private', 'Private Room')
    ])
    submit = SubmitField('Save Table')

    def validate_number(self, field):
        if Table.query.filter_by(number=field.data).first():
            raise ValidationError('This table number already exists.')