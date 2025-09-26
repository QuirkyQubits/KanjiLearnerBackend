from rest_framework import serializers
from kanjilearner.models import DictionaryEntry, PlannedEntry, UserDictionaryEntry


class DictionaryEntrySerializer(serializers.ModelSerializer):
    constituents = serializers.SerializerMethodField()
    visually_similar = serializers.SerializerMethodField()
    used_in = serializers.SerializerMethodField()
    srs_stage = serializers.SerializerMethodField()
    next_review_at = serializers.SerializerMethodField()
    unlocked = serializers.SerializerMethodField()

    class Meta:
        model = DictionaryEntry
        fields = [
            'id',
            'literal',
            'meaning',
            "kunyomi_readings",
            "onyomi_readings",
            "reading",
            'entry_type',
            'level',
            'constituents',
            'visually_similar',
            'used_in',
            'pitch_graphs',
            'srs_stage',
            'next_review_at',
            'unlocked',
            'meaning_mnemonic',
            'reading_mnemonic',
            'parts_of_speech',
            'explanation',
            'audio',
        ]

    def get_constituents(self, obj):
        return [
            {
                "id": c.id,
                "literal": c.literal,
                "meaning": c.meaning,
                "entry_type": c.entry_type,
            }
            for c in obj.constituents.all()
        ]

    def get_visually_similar(self, obj):
        return [
            {
                "id": v.id,
                "literal": v.literal,
                "meaning": v.meaning,
                "entry_type": v.entry_type,
            }
            for v in obj.visually_similar.all()
        ]

    def get_used_in(self, obj):
        return [
            {
                "id": u.id,
                "literal": u.literal,
                "meaning": u.meaning,
                "entry_type": u.entry_type,
            }
            for u in obj.used_in.all()
        ]

    def get_user_entry(self, obj):
        entry_map = self.context.get("user_entry_map", {})
        return entry_map.get(obj.id)

    def get_srs_stage(self, obj):
        ude = self.get_user_entry(obj)
        return ude.srs_stage if ude else None

    def get_unlocked(self, obj):
        ude = self.get_user_entry(obj)
        return ude.is_unlocked if ude else False

    def get_next_review_at(self, obj):
        ude = self.get_user_entry(obj)
        return ude.next_review_at if ude else None


class UserDictionaryEntrySerializer(serializers.ModelSerializer):
    entry = DictionaryEntrySerializer(read_only=True)
    in_plan = serializers.SerializerMethodField()

    class Meta:
        model = UserDictionaryEntry
        fields = [
            "entry",
            "srs_stage",
            "unlocked_at",
            "next_review_at",
            "in_plan",
        ]

    def get_in_plan(self, obj):
        return PlannedEntry.objects.filter(user=obj.user, entry=obj.entry).exists()