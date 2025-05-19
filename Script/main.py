from bs4 import BeautifulSoup
import re
import sys
import traceback

def analyze_styles(soup):
    """Analyze CSS styles to dynamically detect block types, text styles, and raw properties."""
    styles_map = {}  # class -> properties_string map

    style_tags = soup.find_all('style')
    for style_tag in style_tags:
        css_text = style_tag.string
        if not css_text:
            continue
        # Remove @import url(...); parts if any, as they can interfere
        css_text = re.sub(r'@import url\(.*?\);', '', css_text)
        css_rules = css_text.split('}')
        for rule in css_rules:
            if '{' not in rule:
                continue
            selector_part, properties_part = rule.split('{', 1)
            selectors = selector_part.split(',')
            for selector in selectors:
                clean_selector = selector.strip()
                if clean_selector.startswith('.'):  # Process class selectors
                    class_name = clean_selector[1:]
                    # More complex selectors like .class1.class2 or .class1 .class2 are not fully handled here.
                    # This assumes simple .className selectors primarily used by GDocs.
                    if ' ' in class_name or '.' in class_name or ':' in class_name: # Skip complex selectors for now
                        continue
                    if class_name and class_name not in styles_map:
                        styles_map[class_name] = properties_part.strip()

    block_types = {}  # e.g., for special colored boxes
    text_styles = {}  # For inline styling like bold, italic

    for class_name, properties in styles_map.items():
        props_lower = properties.lower()
        # Detect block types by background color
        if 'background-color' in props_lower:
            if '#e5f4ea' in props_lower or 'rgb(46, 198, 98)' in props_lower or '#2ec662' in props_lower: # success
                block_types[class_name] = 'success'
            elif '#edf0f5' in props_lower or 'rgb(126, 162, 214)' in props_lower or '#7ea2d6' in props_lower: # info
                block_types[class_name] = 'info'
            elif '#f9f4e4' in props_lower or 'rgb(249, 204, 44)' in props_lower or '#f9cc2c' in props_lower: # warning
                block_types[class_name] = 'warning'
            elif '#f7e5e5' in props_lower or 'rgb(233, 52, 52)' in props_lower or '#e93434' in props_lower: # danger
                block_types[class_name] = 'danger'
            elif '#d9d9d9' in props_lower or 'rgb(217, 217, 217)' in props_lower: # quote
                block_types[class_name] = 'quote'

        # Detect text styles (inline)
        if 'font-weight:700' in props_lower or 'font-weight:bold' in props_lower:
            text_styles[class_name] = 'bold'
        elif 'font-style:italic' in props_lower:
            text_styles[class_name] = 'italic'
        elif 'text-decoration:line-through' in props_lower or 'text-decoration-line: line-through' in props_lower:
            text_styles[class_name] = 'strike'

    return {'blocks': block_types, 'text': text_styles, 'raw_styles': styles_map}


def process_text(element, text_styles_info, raw_styles_info):
    """
    Processes an element's content to extract text and apply markdown for inline styles and links.
    text_styles_info: dict mapping class names to style types like 'bold', 'italic'.
    raw_styles_info: dict mapping class names to their full CSS property strings (passed for future use).
    """
    text_segments = []
    if element is None:
        return ""

    for content in element.contents:
        if content.name is None:  # NavigableString (text node)
            text_segments.append(str(content))
        elif content.name == 'a':
            href = content.get('href', '')
            if 'google.com/url?' in href:
                match = re.search(r'[?&]q=([^&]+)', href)
                if match:
                    href = match.group(1)
            link_inner_text = process_text(content, text_styles_info, raw_styles_info)
            text_segments.append(f"[{link_inner_text}]({href})")
        elif content.name == 'span':
            span_inner_text = process_text(content, text_styles_info, raw_styles_info)

            style_applied = False
            classes = content.get('class', [])
            for class_name in classes:
                if class_name in text_styles_info:
                    style_type = text_styles_info[class_name]
                    if style_type == 'bold':
                        text_segments.append(f"**{span_inner_text}**")
                    elif style_type == 'italic':
                        text_segments.append(f"*{span_inner_text}*")
                    elif style_type == 'strike':
                        text_segments.append(f"~~{span_inner_text}~~")
                    else:
                        text_segments.append(span_inner_text) # Fallback for unknown defined styles
                    style_applied = True
                    break
            if not style_applied:
                text_segments.append(span_inner_text)
        elif content.name == 'br':
            text_segments.append("  \n")
        else:
            # For other tags, recursively call process_text to handle their content
            text_segments.append(process_text(content, text_styles_info, raw_styles_info))


    return "".join(text_segments)


def process_table(table, text_styles):
    rows = []
    for tr in table.find_all('tr'):
        row = []
        for td in tr.find_all(['td', 'th']):
            # Process each cell content with proper text styling
            cell_text = []
            for content in td.contents:
                if content.name is None:  # Text node
                    cell_text.append(str(content).strip())
                elif content.name == 'span':
                    classes = content.get('class', [])
                    content_text = content.get_text().strip()

                    # Apply text styles
                    style = None
                    for class_ in classes:
                        if class_ in text_styles:
                            style = text_styles[class_]
                            break

                    if style == 'bold':
                        cell_text.append(f"**{content_text}**")
                    elif style == 'italic':
                        cell_text.append(f"*{content_text}*")
                    elif style == 'strike':
                        cell_text.append(f"~~{content_text}~~")
                    else:
                        cell_text.append(content_text)
                elif content.name == 'a':  # Links
                    href = content.get('href', '')
                    # Clean Google tracking from URL
                    if 'google.com/url?' in href:
                        match = re.search(r'q=([^&]+)', href)
                        if match:
                            href = match.group(1)
                    cell_text.append(f"[{content.get_text()}]({href})")
                else:
                    cell_text.append(content.get_text().strip())

            # Join all cell content and clean up
            cell_content = ' '.join(cell_text).strip()
            row.append(cell_content)

        if any(cell.strip() for cell in row):  # Only add non-empty rows
            rows.append(row)

    if not rows or len(rows) < 1:
        return ''

    # Create markdown table
    table_md = []

    # Header row
    if rows:
        table_md.append('| ' + ' | '.join(rows[0]) + ' |')
        # Alignment row
        table_md.append('| ' + ' | '.join([':----' for _ in rows[0]]) + ' |')

    # Data rows
    for row in rows[1:]:
        table_md.append('| ' + ' | '.join(row) + ' |')

    return '\n'.join(table_md)

def process_list(list_element, text_styles_info, raw_styles_info, indent_level=0):
    items_md = []
    is_ordered = list_element.name == 'ol'
    indent_space = "  " * indent_level # Two spaces per indent level

    start_number = 1
    if is_ordered and list_element.has_attr('start'):
        try:
            start_number = int(list_element['start'])
        except ValueError:
            pass # Keep default start_number = 1

    for i, li in enumerate(list_element.find_all('li', recursive=False)):
        item_parts = []
        has_nested_list = False
        for child in li.children:
            if child.name in ['ul', 'ol']:
                nested_list_md = process_list(child, text_styles_info, raw_styles_info, indent_level + 1)
                item_parts.append("\n" + nested_list_md) # Add newline before nested list
                has_nested_list = True
            elif child.name == 'p': # Paragraph within a list item
                # If it's the only child or first child, its text becomes the item text
                # otherwise, it's a multi-paragraph item, needing careful newline handling.
                p_text = process_text(child, text_styles_info, raw_styles_info).strip()
                if p_text:
                    item_parts.append(p_text)
            elif child.name is None: # Text node
                item_parts.append(str(child).strip())
            else: # Other elements
                item_parts.append(process_text(child, text_styles_info, raw_styles_info).strip())

        # Join parts, handling potential leading/trailing newlines from nested lists
        full_item_text = " ".join(filter(None, [part.strip() if not part.startswith("\n") else part for part in item_parts])).strip()

        # If item_text is empty but it contained a nested list, it's not truly empty.
        if not full_item_text and not has_nested_list:
            continue # Skip completely empty LIs without nested content

        prefix = f"{start_number + i}." if is_ordered else "-"
        # Ensure text for list items is on the same line as the marker, unless it's a nested list starting immediately
        if full_item_text.startswith("\n"): # Nested list starting
             items_md.append(f"{indent_space}{prefix}{full_item_text}")
        else:
             items_md.append(f"{indent_space}{prefix} {full_item_text}")


    return '\n'.join(items_md)


def gdocs_to_wikijs(html_content):
    # FIXME: By removing html_content 2 lines below, it will render
    # code blocks, but it's pending to debug why it sometimes takes
    # the following line inside the code block.
    html_content = html_content.replace('&#60418;', '')
    html_content = html_content.replace('&#60419;', '')
    soup = BeautifulSoup(html_content, 'html.parser')
    style_info = analyze_styles(soup)

    for tag in soup.find_all(['head', 'style']):
        tag.decompose()

    output = []
    last_element_was_header = False
    in_code_block = False
    code_block_content = []

    # Iterate over direct children of the body tag
    for element in soup.body.find_all(recursive=False):
        if element.name is None and not element.string.strip():
            continue

        # Handle text nodes found directly under body as paragraphs
        if element.name is None and element.string.strip():
            # Add spacing if needed before this "paragraph"
            if output and not last_element_was_header and not output[-1].endswith('\n\n'):
                 output.append('\n') # Ensure one blank line
            output.append(element.string.strip() + "\n")
            last_element_was_header = False
            continue

        element_text_for_markers = element.get_text(separator=' ', strip=True)

        # --- Code Block Handling ---
        if in_code_block:
            if '' in element_text_for_markers or '🡄' in element_text_for_markers:
                in_code_block = False
                line_content = element.get_text()
                print(line_content)
                clean_line = line_content.replace('', '').replace('🡄', '').strip()
                if clean_line: # Add content on the marker line itself if any
                    code_block_content.append(clean_line)

                if code_block_content:
                    code_text = '\n'.join(code_block_content) # Don't strip internal newlines yet
                    lang_hint = ""
                    if any(keyword in code_text for keyword in ['def ', 'print(', 'import ', 'class ', 'if ', 'for ', 'while ']):
                        lang_hint = "py"
                    output.append(f"```{lang_hint}\n{code_text.strip()}\n```\n") # Strip final code_text
                code_block_content = []
                last_element_was_header = False
                continue
            else:
                code_block_content.append(element.get_text())
                last_element_was_header = False
                continue

        if '' in element_text_for_markers or '🡆' in element_text_for_markers:
            if output and not last_element_was_header and not output[-1].endswith('\n\n'):
                output.append('\n')
            in_code_block = True
            code_block_content = []
            line_content = element.get_text()
            clean_line = line_content.replace('', '').replace('🡆', '').strip()
            if clean_line:
                code_block_content.append(clean_line)
            last_element_was_header = False
            continue
        # --- End Code Block Handling ---

        current_element_is_header = False
        # Add a single blank line between block elements, unless previous was a header.
        if output and not last_element_was_header :
            if not output[-1].endswith('\n\n'): # If not already two newlines
                if output[-1].endswith('\n'):
                    output[-1] = output[-1] + '\n' # Add one more to make it two
                else: # Should not happen if previous elements always add \n
                    output.append('\n\n')
        elif not output and element.name: # First element, no newline needed before it.
            pass


        if element.name and element.name.startswith('h') and len(element.name) > 1 and element.name[1].isdigit():
            level = int(element.name[1])
            header_text = process_text(element, style_info['text'], style_info['raw_styles']).strip()
            if header_text:
                output.append(f"{'#' * level} {header_text}\n")
                current_element_is_header = True

        elif element.name == 'p' and element.find('img', recursive=True): # Image directly in P
            img_tag = element.find('img', recursive=True) # Check only direct children
            # Also consider if P has no other significant text content
            text_around_img = element.get_text(separator='', strip=True)
            img_alt_text = img_tag.get('alt', '') if img_tag else ''
            is_just_image_para = not text_around_img or text_around_img == img_alt_text


            if img_tag and is_just_image_para:
                src = img_tag.get('src', '')
                alt_text = img_alt_text if img_alt_text else 'image'
                if 'images/' in src:
                    src = src.replace('images/', '/')

                centered = False
                p_classes = element.get('class', [])
                for p_class in p_classes:
                    if p_class in style_info['raw_styles'] and \
                       'text-align:center' in style_info['raw_styles'][p_class].lower():
                        centered = True
                        break

                md_img = f"![{alt_text}]({src})"
                if centered:
                    md_img += "{.is-centered}"
                output.append(md_img + "\n")
                current_element_is_header = False
            else: # Paragraph with an image but also other text, or image not direct child. Treat as normal P.
                # This will fall through to the generic 'p' handler below.
                pass # Let it be handled by generic 'p' if not a dedicated image paragraph

        # Ensure 'p' handler is checked after specific 'p' with image
        if element.name == 'p' and not (element.find('img', recursive=False) and is_just_image_para): # Generic Paragraphs
            paragraph_text = process_text(element, style_info['text'], style_info['raw_styles']).strip()

            if not paragraph_text:
                last_element_was_header = False # Keep it false if para is skipped
                continue

            block_type_class = None
            p_classes = element.get('class', [])
            for p_class in p_classes:
                if p_class in style_info['blocks']:
                    block_type_class = style_info['blocks'][p_class]
                    break

            if block_type_class:
                output.append(f"> {paragraph_text}\n> {{.is-{block_type_class}}}\n")
            else:
                output.append(paragraph_text + "\n")
            current_element_is_header = False

        elif element.name == 'table':
            table_md = process_table(element, style_info['text'])
            if table_md:
                output.append(table_md + "\n")
            current_element_is_header = False

        elif element.name == 'hr':
            output.append('\n---\n')
            current_element_is_header = False

        elif element.name in ['ul', 'ol']:
            list_md = process_list(element, style_info['text'], style_info['raw_styles'])
            if list_md:
                output.append(list_md + "\n")
            current_element_is_header = False

        elif not current_element_is_header and element.name not in ['p', 'table', 'hr', 'ul', 'ol'] and not element.name.startswith('h'):
            # Fallback for other unhandled elements if they were not processed above
            unhandled_text = process_text(element, style_info['text'], style_info['raw_styles']).strip()
            if unhandled_text:
                output.append(unhandled_text + "\n")
            current_element_is_header = False # Ensure it's false

        last_element_was_header = current_element_is_header

    final_output = "".join(output)
    final_output = re.sub(r'\n{3,}', '\n\n', final_output)
    final_output = final_output.strip()
    if final_output: # Add a single trailing newline if there's content
        final_output += "\n"

    return final_output


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python gdocs_to_wikijs.py input.html output.md")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        markdown_output = gdocs_to_wikijs(html_content)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown_output)

        print(f"Successfully converted {input_file} to {output_file}")

    except FileNotFoundError:
        print(f"Error: File '{input_file}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        print("Traceback:")
        traceback.print_exc()
        sys.exit(1)