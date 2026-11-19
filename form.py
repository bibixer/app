from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, SubmitField, PasswordField, DateField, HiddenField
from wtforms.validators import DataRequired,InputRequired,Length
from uuid import uuid4

class WriteForm(FlaskForm):
    submission_token = HiddenField(default=lambda: uuid4().hex, validators=[DataRequired(), Length(max=128)])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.is_submitted() and not self.submission_token.raw_data:
            self.submission_token.data = None


class SimpleProductForm(WriteForm):
    name = StringField('Product name', validators=[DataRequired(), Length(max=50)])
    aliases = TextAreaField('Aliases (one per line or separated by commas)')
    submit = SubmitField('Save product and set rates')


class Outworker_form(WriteForm):
    name = StringField(
        "Name",
        validators=[DataRequired()],
    )
    address = StringField("address",validators=[DataRequired()],render_kw={"placeholder": "Enter address"}
                          )
    number =  StringField(
        "Mobile Number",
        validators=[DataRequired()],
        render_kw={"placeholder": "Enter 10-digit mobile number", "inputmode": "numeric",
                   "autocomplete": "tel-national", "pattern": "[0-9]{10}"}
    )
    submit = SubmitField(
        "Submit",
        render_kw={
            "class": "button"
        }
    )
class Return_form(FlaskForm):
    jobcard_id = IntegerField(
        "Job card number",
        validators=[InputRequired()],
        render_kw={"placeholder": "Enter job card number", "min": 1, "id": "jobcard_id"}
    )
    submit = SubmitField(
        "Submit",
        render_kw={
            "class": "button"
        })

class Login_form(FlaskForm):
        user_name = StringField(
            'User Name',
            validators=[DataRequired()],
            render_kw={
                'placeholder': 'Enter User Name',

            })

        password = PasswordField(
            'Password',
            validators=[DataRequired()],
            render_kw={
                'placeholder': 'Enter Password'
            })
        submit = SubmitField(
            'Login',
            render_kw={"class": "button"})
class Date_form_with_name(FlaskForm):
    date_from = DateField(
        label="Date from",
        validators=[DataRequired()]
    )
    date_to = DateField(
        label="Date to",
        validators=[DataRequired()],
    )
    name = StringField(label="Name",validators=[DataRequired()],render_kw={'id':'name_f'})
    submit = SubmitField(
        'Submit',
        render_kw={"class": "button"})

class EditEntryForm(WriteForm):
    version = HiddenField(validators=[DataRequired()])
    submit = SubmitField("Save changes", render_kw={"class": "button"})
