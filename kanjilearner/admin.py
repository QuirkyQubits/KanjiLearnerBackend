from django.contrib import admin
from django import forms
from django.contrib.postgres.forms import SimpleArrayField
from .models import DictionaryEntry, UserDictionaryEntry
from kanjilearner.constants import EntryType


class PitchGraphField(forms.CharField):
    """
    Accepts strings like 'LHH(L)' and converts them into [["L","H","H","(L)"]].
    Also handles DB list values by showing them nicely in the admin form.
    """
    def to_python(self, value):
        if not value:
            return []
        if isinstance(value, list):
            # Already parsed from DB → just return
            return value

        graphs = []
        for raw in value.split(","):
            raw = raw.strip()
            graph = []
            i = 0
            while i < len(raw):
                if raw[i] in ("L", "H"):
                    graph.append(raw[i])
                    i += 1
                elif raw[i] == "(":
                    if raw[i:i+3] == "(L)":
                        graph.append("(L)")
                        i += 3
                    else:
                        raise forms.ValidationError(f"Invalid token near: {raw[i:]}")
                else:
                    raise forms.ValidationError(f"Unexpected character: {raw[i]}")
            graphs.append(graph)
        return graphs

    def prepare_value(self, value):
        """
        Convert [["L","H","H"],["L","H","(L)"]] into 'LHH, LH(L)' for display.
        """
        if isinstance(value, list):
            try:
                return ", ".join("".join(item) for item in value)
            except Exception:
                return str(value)
        return value


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

    reading = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"size": "80"}),
        help_text="Single kana reading for vocab (e.g. たべる)"
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

    pitch_graphs = PitchGraphField(
        required=False,
        help_text="Enter pitch accent graph(s), e.g. LHH or LH(L). "
                  "Separate multiple graphs with commas."
    )

    class Meta:
        model = DictionaryEntry
        fields = "__all__"
    
    def clean_pitch_graphs(self):
        graphs = self.cleaned_data.get("pitch_graphs", [])
        for graph in graphs:
            drop_count = graph.count("(L)")
            if drop_count not in (0, 1):
                raise forms.ValidationError(
                    f"Invalid pitch graph {graph}: must contain either 0 or exactly 1 (L)."
                )
        return graphs

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kunyomi_readings"].help_text = "Separate readings with **English commas**, e.g. く, くだ, おろ"
        self.fields["onyomi_readings"].help_text = "Separate readings with **English commas**, e.g. く, くだ, おろ"


@admin.register(DictionaryEntry)
class DictionaryEntryAdmin(admin.ModelAdmin):
    form = DictionaryEntryForm
    readonly_fields = ['id']
    list_display = ("literal", "entry_type", "meaning", "level")
    search_fields = ("literal", "meaning", "reading")
    list_filter = ("level", "entry_type")
    filter_horizontal = ('constituents', 'visually_similar', 'used_in')

    def get_fieldsets(self, request, obj=None):
        # Base fields always shown
        base_fields = [
            'literal',
            'meaning',
            'level',
            'entry_type',
        ]

        # Add conditional fields
        if obj:
            if obj.entry_type == EntryType.KANJI:
                base_fields += ['kunyomi_readings', 'onyomi_readings']
            elif obj.entry_type == EntryType.VOCAB:
                base_fields += ['reading', 'pitch_graphs', 'explanation', 'parts_of_speech']

        fieldsets = [
            ("Basic Info", {"fields": base_fields}),
        ]

        # Structure only for KANJI or VOCAB
        if obj and obj.entry_type in [EntryType.KANJI, EntryType.VOCAB]:
            fieldsets.append(("Structure", {"fields": ['constituents']}))

        # Mnemonics
        mnemonic_fields = ['meaning_mnemonic']
        if obj and obj.entry_type in [EntryType.KANJI, EntryType.VOCAB]:
            mnemonic_fields.append('reading_mnemonic')
        fieldsets.append(("Mnemonics", {"fields": mnemonic_fields}))

        # Similarity
        fieldsets.append(("Similarity", {"fields": ['visually_similar']}))

        # UsedIn only for radicals + kanji
        if obj and obj.entry_type in [EntryType.RADICAL, EntryType.KANJI]:
            fieldsets.append(("Usage", {"fields": ['used_in']}))

        return fieldsets


    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """
        Restrict the choices shown in M2M fields based on entry_type.
        """
        obj_id = request.resolver_match.kwargs.get("object_id")
        obj = None
        if obj_id:
            try:
                obj = DictionaryEntry.objects.get(pk=obj_id)
            except DictionaryEntry.DoesNotExist:
                pass

        if db_field.name == "constituents" and obj:
            if obj.entry_type == EntryType.KANJI:
                kwargs["queryset"] = DictionaryEntry.objects.filter(entry_type=EntryType.RADICAL)
            elif obj.entry_type == EntryType.VOCAB:
                kwargs["queryset"] = DictionaryEntry.objects.filter(entry_type=EntryType.KANJI)

        if db_field.name == "visually_similar" and obj:
            if obj.entry_type == EntryType.RADICAL:
                kwargs["queryset"] = DictionaryEntry.objects.filter(entry_type=EntryType.RADICAL)
            elif obj.entry_type == EntryType.KANJI:
                kwargs["queryset"] = DictionaryEntry.objects.filter(entry_type=EntryType.KANJI)
            elif obj.entry_type == EntryType.VOCAB:
                kwargs["queryset"] = DictionaryEntry.objects.filter(entry_type=EntryType.VOCAB)

        if db_field.name == "used_in" and obj:
            if obj.entry_type == EntryType.RADICAL:
                kwargs["queryset"] = DictionaryEntry.objects.filter(entry_type=EntryType.KANJI)
            elif obj.entry_type == EntryType.KANJI:
                kwargs["queryset"] = DictionaryEntry.objects.filter(entry_type=EntryType.VOCAB)

        return super().formfield_for_manytomany(db_field, request, **kwargs)


@admin.register(UserDictionaryEntry)
class UserDictionaryEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "entry", "srs_stage", "unlocked_at", "next_review_at")
    list_filter = ("srs_stage",)
    search_fields = ("entry__literal", "user__username")