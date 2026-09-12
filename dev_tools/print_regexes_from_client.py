import pandas

# Read the text file
with open('./resources/regexes_from_client.txt', 'r') as file:
    lines = file.readlines()

# Extract key-value pairs
keys, values = [], []
data_dict = {}
i = 0
for line in lines:
    if line != '' and line != '\n':
        key, value = line.strip().split(':', 1)
        keys.append(key.strip())
        values.append(value.strip())
        data_dict[keys[i]] = values[i]

        print(i)
        i += 1

# Create DataFrame
df = pandas.DataFrame({"Key": keys, "Value": values})

# Print the dataframe, it looks like a table
print(df)

for key in data_dict.keys():
    print(f'"{key}": r"{data_dict[key]}"')

# Print all the keys line by line
print("Keys:")
for key in data_dict.keys():
    print(key)
