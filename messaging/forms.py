from django import forms
from django.contrib.auth.models import User
from .models import Message, TeamMessage


class UserChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        full_name = f"{obj.first_name} {obj.last_name}".strip()
        if full_name:
            return f"{full_name} ({obj.email})"
        return obj.email or obj.username


class StartConversationForm(forms.Form):
    recipient = UserChoiceField(
        queryset=User.objects.none(),
        empty_label='Select a person to message',
        widget=forms.Select(attrs={'class': 'form-select profile-input', 'id': 'recipient-select'})
    )

    def __init__(self, *args, **kwargs):
        allowed_users = kwargs.pop('allowed_users', User.objects.none())
        super().__init__(*args, **kwargs)
        self.fields['recipient'].queryset = allowed_users


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['content', 'attachment']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control profile-input',
                'placeholder': 'Write a message...',
            }),
            'attachment': forms.ClearableFileInput(attrs={
                'class': 'form-control profile-input',
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        content = cleaned_data.get('content')
        attachment = cleaned_data.get('attachment')

        if not content and not attachment:
            raise forms.ValidationError('Please enter a message or attach a file.')

        return cleaned_data


class TeamMessageForm(forms.ModelForm):
    class Meta:
        model = TeamMessage
        fields = ['content', 'attachment']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control profile-input',
                'placeholder': 'Write a message to your team...',
            }),
            'attachment': forms.ClearableFileInput(attrs={
                'class': 'form-control profile-input',
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        content = cleaned_data.get('content')
        attachment = cleaned_data.get('attachment')

        if not content and not attachment:
            raise forms.ValidationError('Please enter a message or attach a file.')

        return cleaned_data