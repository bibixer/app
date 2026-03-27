from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField, SelectField, FloatField, PasswordField, DateField
from wtforms.validators import DataRequired,InputRequired
from datetime import date

class Lump_data(FlaskForm):
    party_name = StringField("party name", validators=[DataRequired()],
                             render_kw={"placeholder": "Enter name of party", "id": "party_name",'disabled': True})
    cuter_name = StringField(
        "Cut By",
        validators=[DataRequired()],
        render_kw={
            "placeholder": "Enter cutter name",
             "id":"cuter_name",'disabled': True
        }
    )

    product_name = StringField(
        "Product Name",
        validators=[DataRequired()],
        render_kw={
            "placeholder": "Enter product name",
             'id':"product_name",'disabled': True
        }
    )

    bundle_type = SelectField(
        "Type of Bundle",
        choices=[
            ("lump", "Lump"),
            ("good_cut", "Good Cut"),
            ("fent", "Fent"),
            ("goodCUT 20 picset", "goodCUT 20 picset"),
            ("fent 20 picset", "fent 20 picset"),
            ("un_cut", "Un Cut")

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
        "Meter of Lump as per bale",
        validators=[DataRequired()],
        render_kw={
            "placeholder": "Enter meter of lump",

        }
    )
    meters_add_remove = FloatField(
        "add or removes",
        validators=[InputRequired()],
        render_kw={
            "placeholder": "Enter meter of lump",

        },
        default=0.0
    )

    numbers_of_bundles = IntegerField(
        "Number of Bundles",
        validators=[DataRequired()],
        render_kw={
            "placeholder": "Enter number of bundles",
             
        },
    default = 2
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

class party_name(FlaskForm):
    name = StringField(
        "Name",
        validators=[DataRequired()],render_kw={"placeholder": "Enter name of party"}
    )
    submit = SubmitField(
        "Submit",
        render_kw={
            "class": "button"
        }
    )
class bale_data_form(FlaskForm):
    party_name = StringField("party name",validators=[DataRequired()],render_kw={"placeholder": "Enter name of party","id":"party_name"},default="UNKNOW")
    lot_number =  IntegerField(
        "Lot Number",
        validators=[InputRequired()],render_kw={"placeholder": "Enter LOT number"},default=9090
    )
    lot_count = IntegerField(
        "Lot Count",
        validators=[DataRequired()],render_kw={"placeholder": "Enter Lot Count"},default=1
    )

    packing_date = DateField('bale date',validators=[DataRequired()],default=date.today)
    bale_number = IntegerField(
        "bale number",
        validators=[DataRequired()],
        render_kw={"placeholder": "Enter bale number"}

    )

    cuter_name = StringField(
        "Cut By",
        validators=[DataRequired()],
        render_kw={
            "placeholder": "Enter cutter name",
            "id": "cuter_name",
        }
    )

    product_name = StringField(
        "Product Name",
        validators=[DataRequired()],
        render_kw={
            "placeholder": "Enter product name",
            'id': "product_name",
        }
    )
    number_lup = IntegerField(
        "lump cut",
        validators=[DataRequired()], render_kw={"placeholder": "Enter lump cut  Count"}
    )
    submit = SubmitField(
        "Submit",
        render_kw={
            "class": "button"
        }
    )

class Find_and_edit(FlaskForm):
    entry_datetime = DateField(label="date of cut")
    cut_by = StringField(
        "Cut By",
        render_kw={
            "placeholder": "Enter cutter name",
            "id": "cuter_name",
        }
    )
    s_no =  IntegerField(label="bundle so_number")
    id= IntegerField(label="bundle id")
    submit = SubmitField(
        "Submit",
        render_kw={
            "class": "button"
        }
    )
class bundle_edit(FlaskForm):
    date_of_entry = DateField(
        "date od entrty",
        validators=[DataRequired()],
        render_kw={
            'disabled': True
           ,
        }
    )
    product_name = StringField(
        "Product Name",
        validators=[DataRequired()],
        render_kw={
            "placeholder": "Enter product name",
            'id': "product_name",
        }
    )
    cut_by = StringField(
        "Cut By",
        render_kw={
            "placeholder": "Enter cutter name",
            "id": "cuter_name",
        }
    )

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