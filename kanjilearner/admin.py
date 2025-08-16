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
    list_display = ("literal", "type", "meaning", "kunyomi_readings", "onyomi_readings", "level", "parts_of_speech", "priority")
    search_fields = ("literal", "meaning", "reading")
    list_filter = ("type", "level")
    filter_horizontal = ('constituents',)

    fieldsets = (
        (None, {
            'fields': ('literal', 'meaning', "kunyomi_readings", "onyomi_readings", 'level', 'priority', 'type')
        }),
        ('Structure', {
            'fields': ('constituents',)
        }),
        ('Mnemonics', {
            'fields': ('meaning_mnemonic', 'reading_mnemonic')
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        # If editing an object and it's not a kanji, hide readings
        if obj and obj.type != "kanji":
            self.exclude = ("kunyomi_readings", "onyomi_readings")
        else:
            self.exclude = None

        return super().get_form(request, obj, **kwargs)

@admin.register(UserDictionaryEntry)
class UserDictionaryEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "entry", "srs_stage", "unlocked", "unlocked_at")
    list_filter = ("srs_stage", "unlocked")
    search_fields = ("entry__literal", "user__username")