from ai_metatagger.utils.state_manager import load_matrix
df = load_matrix()
print(df[df['file_name'].str.contains('Witcher')]['file_name'].unique())
