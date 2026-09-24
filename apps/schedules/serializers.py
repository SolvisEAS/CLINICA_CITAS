from rest_framework import serializers

from .models import AvailabilityException, WeeklySchedule


class WeeklyScheduleSerializer(serializers.ModelSerializer):
    weekday_display = serializers.CharField(source="get_weekday_display", read_only=True)

    class Meta:
        model = WeeklySchedule
        fields = ["id", "doctor", "weekday", "weekday_display", "start_time", "end_time", "active"]

    def validate(self, attrs):
        start = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start and end and end <= start:
            raise serializers.ValidationError("La hora de fin debe ser posterior a la hora de inicio.")
        return attrs


class AvailabilityExceptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailabilityException
        fields = ["id", "doctor", "start_datetime", "end_datetime", "type", "reason"]

    def validate(self, attrs):
        start = attrs.get("start_datetime", getattr(self.instance, "start_datetime", None))
        end = attrs.get("end_datetime", getattr(self.instance, "end_datetime", None))
        if start and end and end <= start:
            raise serializers.ValidationError("'end_datetime' debe ser posterior a 'start_datetime'.")
        return attrs


class AvailableSlotSerializer(serializers.Serializer):
    start_datetime = serializers.DateTimeField()
    end_datetime = serializers.DateTimeField()
