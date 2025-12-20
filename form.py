from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField, SelectField,FloatField
from wtforms.validators import DataRequired,regexp


class Lump_data(FlaskForm):

    cuter_name = StringField(
        "Cut By",
        validators=[DataRequired()],
        render_kw={
            "placeholder": "Enter cutter name",
             
        }
    )

    product_name = StringField(
        "Product Name",
        validators=[DataRequired()],
        render_kw={
            "placeholder": "Enter product name",
             
        }
    )

    bundle_type = SelectField(
        "Type of Bundle",
        choices=[
            ("lump", "Lump"),
            ("good_cut", "Good Cut"),
            ("fent", "Fent"),
            ("un_cut", "Un Cut")
        ],
        validators=[DataRequired()],
        render_kw={
            "class": "form-select"
        }
    )

    meters = FloatField(
        "Meter of Lump",
        validators=[DataRequired()],
        render_kw={
            "placeholder": "Enter meter of lump",
             
        }
    )

    colors = StringField(
        "Color of Lump",
        validators=[DataRequired()],
        render_kw={
            "placeholder": "Enter color of lump",
             
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
    no_of_pics = IntegerField("Number of Pics", validators=[DataRequired()],render_kw={"placeholder": "Enter number of pics"})
    kg_of_bundle = FloatField("kg",validators=[DataRequired()],render_kw={"placeholder": "Enter kg"})
    submit = SubmitField(
        "Submit",
        render_kw={
            "class": "button"
        }
    )
