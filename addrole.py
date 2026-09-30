@bot.tree.command(name="addrole", description="إضافة رتبة لعضو بتصميم إيمبد احترافي")
@app_commands.checks.has_permissions(manage_roles=True)
async def addrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.add_roles(role)
    
    embed = discord.Embed(
        title="✅ ╎ تـم إضـافـة رتـبـة جـديـدة 〣 ｢🎨｣",
        description=f"> تم منح رتبة بنجاح وتحديث صلاحيات العضو.\n━━━━━━━━━━━━━━━━━━━━━",
        color=0x2b2d31,
        timestamp=datetime.datetime.utcnow()
    )
    embed.add_field(name="👤 ╎ الـعـضـو", value=f"> ｢ {member.mention} ｣", inline=False)
    embed.add_field(name="🎨 ╎ الـرتبة المضافة", value=f"> ｢ {role.mention} ｣", inline=False)
    embed.add_field(name="🛡️ ╎ الـمـسـؤول", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
    embed.set_footer(text="Z I UO - MC Server ✦ Roles System")
    
    await interaction.response.send_message(embed=embed)
    