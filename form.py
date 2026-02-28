from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField, SelectField, FloatField, PasswordField, DateField
from wtforms.validators import DataRequired


class Lump_data(FlaskForm):

    cuter_name = StringField(
        "Cut By",
        validators=[DataRequired()],
        render_kw={
            "placeholder": "Enter cutter name",
             "id":"cuter_name",
        }
    )

    product_name = StringField(
        "Product Name",
        validators=[DataRequired()],
        render_kw={
            "placeholder": "Enter product name",
             'id':"product_name",
        }
    )

    bundle_type = SelectField(
        "Type of Bundle",
        choices=[
            ("lump", "Lump"),
            ("good_cut", "Good Cut"),
            ("fent", "Fent"),
            ("un_cut", "Un Cut"),
            ("fent 20 picset", "fent 20 picset"),
            ("goodCUT 20 picset", "goodCUT 20 picset")
        ],
        validators=[DataRequired()],
        render_kw={
            "class": "form-select"
        }
    )



    colors = StringField(
        "Color of Lump",
        validators=[DataRequired()],
        render_kw={
            "placeholder": "Enter color of lump",
             
        }
    )
    meters = FloatField(
        "Meter of Lump",
        validators=[DataRequired()],
        render_kw={
            "placeholder": "Enter meter of lump",

        }
    )
    numbers_of_bundles = IntegerField(
        "Number of Bundles",
        validators=[DataRequired()],
        render_kw={
            "placeholder": "Enter number of bundles",
             
        }
    )
    submit = SubmitField(
        "next",
        render_kw={
            "class": "button"
        }
    )


class bundle_invadata(FlaskForm):
    no_of_so = IntegerField("sn.o", validators=[DataRequired()],
                              render_kw={"placeholder": "Enter number of pics"})
    no_of_pics = IntegerField("Number of Pics", validators=[DataRequired()],render_kw={"placeholder": "Enter number of pics"})
    kg_of_bundle = FloatField("kg",validators=[DataRequired()],render_kw={"placeholder": "Enter kg"})
    submit = SubmitField(
        "Submit",
        render_kw={
            "class": "button"
        }
    )
class Item_data(FlaskForm):
    name = StringField(
        "Name",
        validators=[DataRequired()],

    )
    size = FloatField(
        "Size",
        validators=[DataRequired()], )
    meter = FloatField('meter',validators=[DataRequired()],render_kw={"placeholder": "Enter meter"}

    )
    submit  = SubmitField(
        "Submit",
        render_kw={
            "class": "button"
        }
    )

class Outworker_form(FlaskForm):
    name = StringField(
        "Name",
        validators=[DataRequired()],
    )
    address = StringField("address",validators=[DataRequired()],render_kw={"placeholder": "Enter address"}
                          )
    number =  IntegerField(
        "Mobile Number",
        validators=[DataRequired()] ,render_kw={"placeholder": "Enter mobile number"}
    )
    submit = SubmitField(
        "Submit",
        render_kw={
            "class": "button"
        }
    )
class Cutter_form(FlaskForm):
    name = StringField(
        "Name",
        validators=[DataRequired()],
    )
    submit = SubmitField(
        "Submit",
        render_kw={
            "class": "button"
        }
    )
class Return_form(FlaskForm):
    name = StringField(
        "Name",
        render_kw={"placeholder": "Enter name of outworker"
                   ,"id":"job_name"}
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
class Date_form(FlaskForm):
    date_from = DateField(
        label="Date from",
        validators=[DataRequired()]
    )
    date_to = DateField(
        label="Date to",
        validators=[DataRequired()],
    )
    submit = SubmitField(
        'Submit',
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