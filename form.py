from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, SubmitField, SelectField, FloatField, PasswordField, DateField, HiddenField
from wtforms.validators import DataRequired,InputRequired,Length
from datetime import date
from uuid import uuid4
from bundle_types import BUNDLE_TYPE_CHOICES

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


class Lump_data(WriteForm):
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
        choices=BUNDLE_TYPE_CHOICES,
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


class bundle_invadata(WriteForm):
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
class Item_data(WriteForm):
    name = StringField(
        "Name",
        validators=[DataRequired()],

    )
    aliases = TextAreaField(
        "Aliases (comma or new line separated)",
        render_kw={"placeholder": "Example: VIMAL 2M, VIMAL TWO METER"},
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

class Outworker_form(WriteForm):
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
class Cutter_form(WriteForm):
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

class party_name(WriteForm):
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
class bale_data_form(WriteForm):
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


class EditEntryForm(WriteForm):
    version = HiddenField(validators=[DataRequired()])
    submit = SubmitField("Save changes", render_kw={"class": "button"})



#     cuter_name = StringField(
#         "Cut By",
#         validators=[DataRequired()],
#         render_kw={
#             "placeholder": "Enter cutter name",
#             "id": "cuter_name",
#         }
#     )
#
#     product_name = StringField(
#         "Product Name autoupdate lump and bundle",
#         validators=[DataRequired()],
#         render_kw={
#             "placeholder": "Enter product name",
#             'id': "product_name",
#         }
#     )
#
#     submit = SubmitField(
#         "Update",
#         render_kw={
#             "class": "button"
#         }
#     )
#
# class Lump_update(FlaskForm):
#     cuter_name = StringField(
#         "Cut By",
#         validators=[DataRequired()],
#         render_kw={
#             "placeholder": "Enter cutter name",
#             "id": "cuter_name", 'disabled': True
#         }
#     )
#
#     product_name = StringField(
#         "Product Name",
#         validators=[DataRequired()],
#         render_kw={
#             "placeholder": "Enter product name autoupdate bundle" ,
#             'id': "product_name", 'disabled': True
#         }
#     )
#
#     bundle_type = SelectField(
#         "Type of Bundle autoupdate bundle "  ,
#         choices=[
#             ("lump", "Lump"),
#             ("good_cut", "Good Cut"),
#             ("fent", "Fent"),
#             ("goodCUT 20 picset", "goodCUT 20 picset"),
#             ("fent 20 picset", "fent 20 picset"),
#             ("un_cut", "Un Cut")
#
#         ],
#         validators=[DataRequired()],
#         render_kw={
#             "class": "form-select"
#         }
#     )
#
#     colors = StringField(
#         "Color of Lump autoupdate bundle ",
#         validators=[DataRequired()],
#         render_kw={
#             "placeholder": "Enter color of lump",
#
#         }
#     )
#     meters = FloatField(
#         "Meter of Lump as per bale",
#         validators=[DataRequired()],
#         render_kw={
#             "placeholder": "Enter meter of lump",
#
#         }
#     )
#     meters_add_remove = FloatField(
#         "add or removes",
#         validators=[InputRequired()],
#         render_kw={
#             "placeholder": "Enter meter of lump",
#
#         },
#         default=0.0
#     )
#
#     submit = SubmitField(
#         "update",
#         render_kw={
#             "class": "button"
#         }
#     )
#
# class Bundle_update(FlaskForm):
#
#         no_of_so = IntegerField("sn.o", validators=[DataRequired()],
#                                 render_kw={"placeholder": "Enter so number "})
#         product_name = StringField(
#             "Product Name",
#             validators=[DataRequired()],
#             render_kw={
#                 "placeholder": "Enter product name autoupdate bundle",
#                 'id': "product_name", 'disabled': True
#             }
#         )
#
#         bundle_type = SelectField(
#             "Type of Bundle autoupdate bundle ",
#             choices=[
#                 ("lump", "Lump"),
#                 ("good_cut", "Good Cut"),
#                 ("fent", "Fent"),
#                 ("goodCUT 20 picset", "goodCUT 20 picset"),
#                 ("fent 20 picset", "fent 20 picset"),
#                 ("un_cut", "Un Cut")
#
#             ],
#             validators=[DataRequired()],
#             render_kw={
#                 "class": "form-select"
#             }
#         )
#         no_of_pics = IntegerField("Number of Pics", validators=[DataRequired()],
#                                   render_kw={"placeholder": "Enter number of pics"})
#         kg_of_bundle = FloatField("kg", validators=[DataRequired()], render_kw={"placeholder": "Enter kg"})
#
#         given_to_  =  StringField(
#             "given to update on job card",
#             validators=[DataRequired()],
#             render_kw={
#                 "placeholder": "Enter product name autoupdate bundle",
#                 'id': "product_name", 'disabled': True
#             })
#         submit = SubmitField(
#             "update",
#             render_kw={
#                 "class": "button"
#             }
#         )
