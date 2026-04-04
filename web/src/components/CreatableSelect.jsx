/**
 * A searchable Select that also accepts custom (typed/pasted) values.
 *
 * Built on Mantine's Combobox primitives because the opinionated Select
 * component dropped creatable support in v7+.
 */
import { useState } from "react";
import {
  Combobox,
  InputBase,
  useCombobox,
} from "@mantine/core";

export default function CreatableSelect({
  label,
  placeholder,
  data = [],
  value,
  onChange,
  "data-testid": dataTestId,
}) {
  const combobox = useCombobox({
    onDropdownClose: () => combobox.resetSelectedOption(),
  });

  // Local search state drives the text shown in the input
  const [search, setSearch] = useState(value || "");

  // Find a display label for the current value (if it matches a known option)
  function displayValue(val) {
    const match = data.find((d) => d.value === val);
    return match ? match.label : val || "";
  }

  // Filter options based on current search text
  const filteredOptions = data.filter((item) =>
    item.label.toLowerCase().includes(search.toLowerCase().trim())
  );

  const options = filteredOptions.map((item) => (
    <Combobox.Option value={item.value} key={item.value}>
      {item.label}
    </Combobox.Option>
  ));

  return (
    <Combobox
      store={combobox}
      onOptionSubmit={(val) => {
        onChange(val);
        setSearch(displayValue(val));
        combobox.closeDropdown();
      }}
    >
      <Combobox.Target>
        <InputBase
          label={label}
          placeholder={placeholder}
          rightSection={<Combobox.Chevron />}
          rightSectionPointerEvents="none"
          value={search}
          onChange={(event) => {
            const val = event.currentTarget.value;
            setSearch(val);
            onChange(val);
            combobox.openDropdown();
            combobox.updateSelectedOptionIndex();
          }}
          onClick={() => combobox.openDropdown()}
          onFocus={() => combobox.openDropdown()}
          onBlur={() => {
            combobox.closeDropdown();
            // Keep whatever the user typed/pasted as the value
            if (!search.trim()) {
              onChange("");
            }
          }}
          data-testid={dataTestId}
        />
      </Combobox.Target>

      <Combobox.Dropdown>
        <Combobox.Options>
          {options.length > 0 ? (
            options
          ) : (
            <Combobox.Empty>
              {search.trim()
                ? "No matches -- your input will be used as-is"
                : "No keys available"}
            </Combobox.Empty>
          )}
        </Combobox.Options>
      </Combobox.Dropdown>
    </Combobox>
  );
}