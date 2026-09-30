@bot.tree.command(name="removerole", description="إزالة رتبة من عضو بتصميم احترافي")
@app_commands.checks.has_permissions(manage_roles=True)
async def removerole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.remove_roles(role)
    
    embed = discord.Embed(
        title="❌ ╎ تـم إزالـة رتـبـة من عـضـو 〣 ｢🎨｣",
        description=f"> تم سحب الرتبة بنجاح وتحديث الصلاحيات.\n━━━━━━━━━━━━━━━━━━━━━",
        color=0x2b2d31,
        timestamp=datetime.datetime.utcnow()
    )
    embed.add_field(name="👤 ╎ الـعـضـو", value=f"> ｢ {member.mention} ｣", inline=False)
    embed.add_field(name="🎨 ╎ الرتبة المسحوبة", value=f"> ｢ {role.mention} ｣", inline=False)
    embed.add_field(name="🛡️ ╎ الـمـسـؤول", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
    embed.set_footer(text="Z I UO - MC Server ✦ Roles System")
    
    await interaction.response.send_message(embed=embed)
    