def role_flags(request):
    user = request.user

    return {
        "is_system_admin": (
            user.is_authenticated
            and (
                user.is_superuser
                or user.groups.filter(name="System Admin").exists()
            )
        )
    }
