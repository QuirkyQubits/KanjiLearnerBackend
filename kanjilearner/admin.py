from django.contrib import admin
from django import forms
from django.contrib.postgres.forms import SimpleArrayField
from .models import DictionaryEntry, UserDictionaryEntry

# Custom form for DictionaryEntry
class DictionaryEntryForm(forms.ModelForm):
    kunyomi_readings = SimpleArrayField(
        base_field=forms.CharField(),
        required=False,
        widget=forms.TextInput(attrs={"size": "80"})
    )
    onyomi_readings = SimpleArrayField(
        base_field=forms.CharField(),
        required=False,
        widget=forms.TextInput(attrs={"size": "80"})
    )

    readings = SimpleArrayField(
        base_field=forms.CharField(),
        required=False,
        widget=forms.TextInput(attrs={"size": "80"}),
        help_text="Separate readings with **English commas**, e.g. たべる, みず"
    )

    explanation = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Explain the vocab’s usage, nuances, or when to use each reading."
    )

    parts_of_speech = forms.MultipleChoiceField(
        choices=DictionaryEntry.PARTS_OF_SPEECH_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select one or more parts of speech (e.g. noun, suru_noun)"
    )

    class Meta:
        model = DictionaryEntry
        fields = "__all__"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kunyomi_readings"].help_text = "Separate readings with **English commas**, e.g. く, くだ, おろ"
        self.fields["onyomi_readings"].help_text = "Separate readings with **English commas**, e.g. く, くだ, おろ"


@admin.register(DictionaryEntry)
class DictionaryEntryAdmin(admin.ModelAdmin):
    form = DictionaryEntryForm
    readonly_fields = ['id']
    list_display = ("literal", "type", "meaning", "level", "priority")
    search_fields = ("literal", "meaning", "reading")
    list_filter = ("type", "level")
    filter_horizontal = ('constituents',)

    def get_fieldsets(self, request, obj=None):
        # Base fields always shown
        base_fields = [
            'literal',
            'meaning',
            'level',
            'priority',
            'type',
        ]

        # Add conditional fields
        if obj:
            if obj.type == "KANJI":
                base_fields += ['kunyomi_readings', 'onyomi_readings']
            elif obj.type == "VOCAB":
                base_fields += ['readings', 'explanation', 'parts_of_speech']

        fieldsets = [
            ("Basic Info", {"fields": base_fields}),
        ]

        # Structure only for KANJI or VOCAB
        if obj and obj.type in ["KANJI", "VOCAB"]:
            fieldsets.append(("Structure", {"fields": ['constituents']}))

        # Mnemonics
        mnemonic_fields = ['meaning_mnemonic']
        if obj and obj.type in ["KANJI", "VOCAB"]:
            mnemonic_fields.append('reading_mnemonic')

        fieldsets.append(("Mnemonics", {"fields": mnemonic_fields}))

        return fieldsets

@admin.register(UserDictionaryEntry)
class UserDictionaryEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "entry", "srs_stage", "unlocked", "unlocked_at")
    list_filter = ("srs_stage", "unlocked")
    search_fields = ("entry__literal", "user__username")