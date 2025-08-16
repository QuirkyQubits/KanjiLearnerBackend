from rest_framework import serializers
from kanjilearner.models import DictionaryEntry, UserDictionaryEntry


class DictionaryEntrySerializer(serializers.ModelSerializer):
    constituents = serializers.SerializerMethodField()
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
            "readings",  # vocab only
            'entry_type',
            'level',
            'priority',
            'constituents',
            'srs_stage',
            'next_review_at',
            'unlocked',
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

    def get_user_entry(self, obj):
        user = self.context.get('request').user
        try:
            return UserDictionaryEntry.objects.get(user=user, entry=obj)
        except UserDictionaryEntry.DoesNotExist:
            return None

    def get_srs_stage(self, obj):
        ude = self.get_user_entry(obj)
        return ude.srs_stage if ude else None

    def get_unlocked(self, obj):
        ude = self.get_user_entry(obj)
        return ude.is_unlocked if ude else False

    def get_next_review_at(self, obj):
        ude = self.get_user_entry(obj)
        return ude.next_review_at if ude else None