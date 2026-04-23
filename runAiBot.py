import os
import csv
import re
import pyautogui

csv.field_size_limit(1000000)

from random import choice, shuffle, randint
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.select import Select
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementClickInterceptedException,
    NoSuchWindowException,
    ElementNotInteractableException,
    WebDriverException,
)

from config.personals import *
from config.questions import *
from config.search import *
from config.secrets import use_AI, username, password, ai_provider
from config.settings import *

from modules.open_chrome import *
from modules.helpers import *
from modules.clickers_and_finders import *
from modules.validator import validate_config
from modules.ai.openaiConnections import (
    ai_create_openai_client,
    ai_extract_skills,
    ai_answer_question,
    ai_close_openai_client,
)
from modules.ai.deepseekConnections import (
    deepseek_create_client,
    deepseek_extract_skills,
    deepseek_answer_question,
)
from modules.ai.geminiConnections import (
    gemini_create_client,
    gemini_extract_skills,
    gemini_answer_question,
)

from typing import Literal

# Disable pyautogui failsafe
pyautogui.FAILSAFE = False

# Override pause settings if running in background
if run_in_background:
    pause_at_failed_question = False
    pause_before_submit = False
    run_non_stop = False

# Build full name from parts
_first = first_name.strip()
_middle = middle_name.strip()
_last = last_name.strip()
full_name = f"{_first} {_middle} {_last}".strip() if _middle else f"{_first} {_last}".strip()

# Application state flags
use_new_resume_flag = True
randomly_filled_questions = set()

tabs_open_count = 1
successful_easy_applies = 0
external_link_collected_count = 0
failed_application_count = 0
skipped_job_count = 0
daily_easy_apply_cap_reached = False

# Regular expression for extracting years of experience
experience_regex = re.compile(r'[(]?\s*(\d+)\s*[)]?\s*[-to]*\s*\d*[+]*\s*year[s]?', re.IGNORECASE)

# Salary and notice period calculations
desired_salary_in_lakhs = str(round(desired_salary / 100000, 2))
desired_salary_per_month = str(round(desired_salary / 12, 2))
desired_salary_str = str(desired_salary)

current_ctc_in_lakhs = str(round(current_ctc / 100000, 2))
current_ctc_per_month = str(round(current_ctc / 12, 2))
current_ctc_str = str(current_ctc)

notice_period_in_months = str(notice_period // 30)
notice_period_in_weeks = str(notice_period // 7)
notice_period_str = str(notice_period)

# AI client and context
ai_client_instance = None
company_info_for_ai = None


def verify_logged_in_linkedin() -> bool:
    """Check if user is currently logged into LinkedIn."""
    current_url = driver.current_url
    if current_url == "https://www.linkedin.com/feed/":
        return True
    if try_linkText(driver, "Sign in"):
        return False
    if try_xp(driver, '//button[@type="submit" and contains(text(), "Sign in")]'):
        return False
    if try_linkText(driver, "Join now"):
        return False
    print_lg("Sign in link not found, assuming user is already logged in.")
    return True


def perform_linkedin_login() -> None:
    """Log into LinkedIn using provided credentials."""
    driver.get("https://www.linkedin.com/login")
    try:
        wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Forgot password?")))
        try:
            text_input_by_ID(driver, "username", username, 1)
        except Exception:
            print_lg("Could not locate username input field.")
        try:
            text_input_by_ID(driver, "password", password, 1)
        except Exception:
            print_lg("Could not locate password input field.")
        driver.find_element(By.XPATH, '//button[@type="submit" and contains(text(), "Sign in")]').click()
    except Exception:
        try:
            profile_btn = find_by_class(driver, "profile__details")
            profile_btn.click()
        except Exception:
            print_lg("Login attempt failed!")

    try:
        wait.until(EC.url_to_be("https://www.linkedin.com/feed/"))
        print_lg("Login successful.")
    except Exception:
        print_lg("Login may have failed. Trying manual retry.")
        manual_login_retry(verify_logged_in_linkedin, 2)


def fetch_previously_applied_job_ids() -> set:
    """Read CSV file and return a set of already applied job IDs."""
    applied_ids = set()
    try:
        with open(file_name, 'r', encoding='utf-8') as csv_file:
            reader = csv.reader(csv_file)
            for row in reader:
                applied_ids.add(row[0])
    except FileNotFoundError:
        print_lg(f"CSV file '{file_name}' does not exist.")
    return applied_ids


def configure_search_location() -> None:
    """Set the location filter on LinkedIn job search."""
    if not search_location.strip():
        return
    print_lg(f'Setting location to: "{search_location.strip()}"')
    try:
        location_input = try_xp(driver, ".//input[@aria-label='City, state, or zip code'and not(@disabled)]", False)
        text_input(actions, location_input, search_location, "Search Location")
    except ElementNotInteractableException:
        try_xp(driver, ".//label[@class='jobs-search-box__input-icon jobs-search-box__keywords-label']")
        actions.send_keys(Keys.TAB, Keys.TAB).perform()
        actions.key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).perform()
        actions.send_keys(search_location.strip()).perform()
        sleep(2)
        actions.send_keys(Keys.ENTER).perform()
        try_xp(driver, ".//button[@aria-label='Cancel']")
    except Exception as error:
        try_xp(driver, ".//button[@aria-label='Cancel']")
        print_lg("Failed to set location, proceeding with default.", error)


def apply_all_search_filters() -> None:
    """Apply all configured search filters (experience, date posted, etc.)."""
    configure_search_location()
    recommended_delay = 1 if click_gap < 1 else 0

    try:
        wait.until(EC.presence_of_element_located((By.XPATH, '//button[normalize-space()="All filters"]'))).click()
        buffer(recommended_delay)

        wait_span_click(driver, sort_by)
        wait_span_click(driver, date_posted)
        buffer(recommended_delay)

        multi_sel_noWait(driver, experience_level)
        multi_sel_noWait(driver, companies, actions)
        if experience_level or companies:
            buffer(recommended_delay)

        multi_sel_noWait(driver, job_type)
        multi_sel_noWait(driver, on_site)
        if job_type or on_site:
            buffer(recommended_delay)

        if easy_apply_only:
            boolean_button_click(driver, actions, "Easy Apply")

        multi_sel_noWait(driver, location)
        multi_sel_noWait(driver, industry)
        if location or industry:
            buffer(recommended_delay)

        multi_sel_noWait(driver, job_function)
        multi_sel_noWait(driver, job_titles)
        if job_function or job_titles:
            buffer(recommended_delay)

        if under_10_applicants:
            boolean_button_click(driver, actions, "Under 10 applicants")
        if in_your_network:
            boolean_button_click(driver, actions, "In your network")
        if fair_chance_employer:
            boolean_button_click(driver, actions, "Fair Chance Employer")

        wait_span_click(driver, salary)
        buffer(recommended_delay)

        multi_sel_noWait(driver, benefits)
        multi_sel_noWait(driver, commitments)
        if benefits or commitments:
            buffer(recommended_delay)

        show_results_button = driver.find_element(By.XPATH, '//button[contains(@aria-label, "Apply current filters to show")]')
        show_results_button.click()

        global pause_after_filters
        if pause_after_filters:
            user_choice = pyautogui.confirm(
                "These are your configured search results and filters. You may modify them while this dialog is open.",
                "Verify Search Results",
                ["Turn off Pause after search", "Looks good, Continue"]
            )
            if user_choice == "Turn off Pause after search":
                pause_after_filters = False
    except Exception as error:
        print_lg("Failed to apply filters!", error)


def retrieve_pagination_info() -> tuple[WebElement | None, int | None]:
    """Get pagination element and current page number."""
    try:
        pagination = try_find_by_classes(driver, ["jobs-search-pagination__pages", "artdeco-pagination", "artdeco-pagination__pages"])
        scroll_to_view(driver, pagination)
        current_page_num = int(pagination.find_element(By.XPATH, "//button[contains(@class, 'active')]").text)
    except Exception:
        print_lg("Could not locate pagination element; may be at end of results.")
        pagination = None
        current_page_num = None
    return pagination, current_page_num


def extract_job_card_details(job_card: WebElement, blacklist_companies: set, rejected_ids: set) -> tuple[str, str, str, str, str, bool]:
    """Extract basic info from a job card and determine if it should be skipped."""
    job_link_elem = job_card.find_element(By.TAG_NAME, 'a')
    scroll_to_view(driver, job_link_elem, True)
    job_identifier = job_card.get_dom_attribute('data-occludable-job-id')
    title_text = job_link_elem.text.split("\n")[0]
    subtitle_text = job_card.find_element(By.CLASS_NAME, 'artdeco-entity-lockup__subtitle').text
    sep_index = subtitle_text.find(' · ')
    company_name = subtitle_text[:sep_index]
    location_raw = subtitle_text[sep_index + 3:]
    work_type = location_raw[location_raw.rfind('(') + 1:location_raw.rfind(')')]
    location_clean = location_raw[:location_raw.rfind('(')].strip()

    should_skip = False
    if company_name in blacklist_companies:
        print_lg(f'Skipping blacklisted company: "{title_text} | {company_name}" (ID: {job_identifier})')
        should_skip = True
    elif job_identifier in rejected_ids:
        print_lg(f'Skipping previously rejected job: "{title_text} | {company_name}" (ID: {job_identifier})')
        should_skip = True
    try:
        if job_card.find_element(By.CLASS_NAME, "job-card-container__footer-job-state").text == "Applied":
            should_skip = True
            print_lg(f'Already applied: "{title_text} | {company_name}" (ID: {job_identifier})')
    except:
        pass

    if not should_skip:
        try:
            job_link_elem.click()
        except Exception:
            print_lg(f'Failed to click job card for "{title_text} | {company_name}" (ID: {job_identifier})')
            discard_job_modal()
            job_link_elem.click()
    buffer(click_gap)

    return job_identifier, title_text, company_name, location_clean, work_type, should_skip


def screen_company_description(rejected_ids: set, job_id: str, company_name: str, blacklist_companies: set) -> tuple[set, set, WebElement]:
    """Check company description for blacklisted words and return updated sets."""
    top_card = try_find_by_classes(driver, [
        "job-details-jobs-unified-top-card__primary-description-container",
        "job-details-jobs-unified-top-card__primary-description",
        "jobs-unified-top-card__primary-description",
        "jobs-details__main-content"
    ])
    company_section = find_by_class(driver, "jobs-company__box")
    scroll_to_view(driver, company_section)
    company_desc_raw = company_section.text
    company_desc_lower = company_desc_raw.lower()

    skip_blacklist_check = False
    for good_term in about_company_good_words:
        if good_term.lower() in company_desc_lower:
            print_lg(f'Found whitelisted term "{good_term}", skipping blacklist check.')
            skip_blacklist_check = True
            break

    if not skip_blacklist_check:
        for bad_term in about_company_bad_words:
            if bad_term.lower() in company_desc_lower:
                rejected_ids.add(job_id)
                blacklist_companies.add(company_name)
                raise ValueError(f'\n"{company_desc_raw}"\n\nContains blacklisted term "{bad_term}".')

    buffer(click_gap)
    scroll_to_view(driver, top_card)
    return rejected_ids, blacklist_companies, top_card


def parse_years_of_experience(description: str) -> int:
    """Extract required years of experience from job description."""
    matches = re.findall(experience_regex, description)
    if not matches:
        print_lg(f'\n{description}\n\nCould not determine experience requirement!')
        return 0
    valid_years = [int(m) for m in matches if int(m) <= 12]
    return max(valid_years) if valid_years else 0


def extract_job_description_details() -> tuple[
    str | Literal['Unknown'],
    int | Literal['Unknown'],
    bool,
    str | None,
    str | None
]:
    """Extract job description and determine if it should be skipped based on content."""
    job_desc_text = "Unknown"
    required_exp = "Unknown"
    masters_bonus = 0
    skip_job = False
    skip_reason = None
    skip_message = None

    try:
        job_desc_text = find_by_class(driver, "jobs-box__html-content").text
        desc_lower = job_desc_text.lower()

        for forbidden_word in bad_words:
            if forbidden_word.lower() in desc_lower:
                skip_message = f'\n{job_desc_text}\n\nContains prohibited word "{forbidden_word}". Skipping.'
                skip_reason = "Found a Bad Word in About Job"
                skip_job = True
                break

        if not skip_job and not security_clearance and ('polygraph' in desc_lower or 'clearance' in desc_lower or 'secret' in desc_lower):
            skip_message = f'\n{job_desc_text}\n\nMentions clearance/polygraph. Skipping.'
            skip_reason = "Asking for Security clearance"
            skip_job = True

        if not skip_job:
            if did_masters and 'master' in desc_lower:
                print_lg(f'Found "master" in description.')
                masters_bonus = 2
            required_exp = parse_years_of_experience(job_desc_text)
            if current_experience > -1 and required_exp > current_experience + masters_bonus:
                skip_message = f'\n{job_desc_text}\n\nRequired experience {required_exp} exceeds current {current_experience + masters_bonus}. Skipping.'
                skip_reason = "Required experience is high"
                skip_job = True
    except Exception:
        if job_desc_text == "Unknown":
            print_lg("Unable to extract job description!")
        else:
            required_exp = "Error in extraction"
            print_lg("Failed to extract years of experience.")
    finally:
        return job_desc_text, required_exp, skip_job, skip_reason, skip_message


def upload_resume_file(modal_container: WebElement, resume_path: str) -> tuple[bool, str]:
    """Attempt to upload the specified resume file."""
    try:
        modal_container.find_element(By.NAME, "file").send_keys(os.path.abspath(resume_path))
        return True, os.path.basename(default_resume_path)
    except:
        return False, "Previous resume"


def handle_common_question_response(label_text: str, proposed_answer: str) -> str:
    """Modify answer for common question types."""
    if 'sponsorship' in label_text or 'visa' in label_text:
        return require_visa
    return proposed_answer


def fill_application_questions(modal_container: WebElement, questions_set: set, job_location: str, job_description: str | None = None) -> set:
    """Iterate through all questions in the Easy Apply modal and answer them."""
    all_question_elements = modal_container.find_elements(By.XPATH, ".//div[@data-test-form-element]")

    for question_element in all_question_elements:
        # Handle dropdowns
        select_element = try_xp(question_element, ".//select", False)
        if select_element:
            label_raw = "Unknown"
            try:
                label_tag = question_element.find_element(By.TAG_NAME, "label")
                label_raw = label_tag.find_element(By.TAG_NAME, "span").text
            except:
                pass
            answer_value = 'Yes'
            label_lower = label_raw.lower()
            select_obj = Select(select_element)
            currently_selected = select_obj.first_selected_option.text
            option_texts = []
            options_display = '"List of phone country codes"'
            if label_lower != "phone country code":
                option_texts = [opt.text for opt in select_obj.options]
                options_display = "".join([f' "{opt}",' for opt in option_texts])
            previous_answer = currently_selected

            if overwrite_previous_answers or currently_selected == "Select an option":
                if 'email' in label_lower or 'phone' in label_lower:
                    answer_value = previous_answer
                elif 'gender' in label_lower or 'sex' in label_lower:
                    answer_value = gender
                elif 'disability' in label_lower:
                    answer_value = disability_status
                elif 'proficiency' in label_lower:
                    answer_value = 'Professional'
                elif any(loc in label_lower for loc in ['location', 'city', 'state', 'country']):
                    if 'country' in label_lower:
                        answer_value = country
                    elif 'state' in label_lower:
                        answer_value = state
                    elif 'city' in label_lower:
                        answer_value = current_city if current_city else job_location
                    else:
                        answer_value = job_location
                else:
                    answer_value = handle_common_question_response(label_lower, answer_value)

                try:
                    select_obj.select_by_visible_text(answer_value)
                except NoSuchElementException:
                    possible_phrases = []
                    if answer_value == 'Decline':
                        possible_phrases = ["Decline", "not wish", "don't wish", "Prefer not", "not want"]
                    elif 'yes' in answer_value.lower():
                        possible_phrases = ["Yes", "Agree", "I do", "I have"]
                    elif 'no' in answer_value.lower():
                        possible_phrases = ["No", "Disagree", "I don't", "I do not"]
                    else:
                        possible_phrases = [answer_value, answer_value.lower(), answer_value.upper(), ''.join(c for c in answer_value if c.isalnum())]

                    matched = False
                    for phrase in possible_phrases:
                        for opt_text in option_texts:
                            if phrase.lower() in opt_text.lower() or opt_text.lower() in phrase.lower():
                                select_obj.select_by_visible_text(opt_text)
                                answer_value = opt_text
                                matched = True
                                break
                    if not matched:
                        print_lg(f'No matching option for "{answer_value}" in "{label_raw}", answering randomly.')
                        select_obj.select_by_index(randint(1, len(select_obj.options) - 1))
                        answer_value = select_obj.first_selected_option.text
                        randomly_filled_questions.add((f'{label_raw} [ {options_display} ]', "select"))
            questions_set.add((f'{label_raw} [ {options_display} ]', answer_value, "select", previous_answer))
            continue

        # Handle radio buttons
        radio_fieldset = try_xp(question_element, './/fieldset[@data-test-form-builder-radio-button-form-component="true"]', False)
        if radio_fieldset:
            previous_answer = None
            label_elem = try_xp(radio_fieldset, './/span[@data-test-form-builder-radio-button-form-component__title]', False)
            try:
                label_elem = find_by_class(label_elem, "visually-hidden", 2.0)
            except:
                pass
            label_raw = label_elem.text if label_elem else "Unknown"
            answer_value = 'Yes'
            label_lower = label_raw.lower()
            label_raw += ' [ '
            radio_options = radio_fieldset.find_elements(By.TAG_NAME, 'input')
            option_labels_list = []

            for opt in radio_options:
                opt_id = opt.get_attribute("id")
                opt_label = try_xp(radio_fieldset, f'.//label[@for="{opt_id}"]', False)
                opt_label_text = f'"{opt_label.text if opt_label else "Unknown"}"<{opt.get_attribute("value")}>'
                option_labels_list.append(opt_label_text)
                if opt.is_selected():
                    previous_answer = opt_label_text
                label_raw += f' {opt_label_text},'

            if overwrite_previous_answers or previous_answer is None:
                if 'citizenship' in label_lower or 'employment eligibility' in label_lower:
                    answer_value = us_citizenship
                elif 'veteran' in label_lower or 'protected' in label_lower:
                    answer_value = veteran_status
                elif 'disability' in label_lower or 'handicapped' in label_lower:
                    answer_value = disability_status
                else:
                    answer_value = handle_common_question_response(label_lower, answer_value)

                found_option = try_xp(radio_fieldset, f".//label[normalize-space()='{answer_value}']", False)
                if found_option:
                    actions.move_to_element(found_option).click().perform()
                else:
                    possible_phrases = ["Decline", "not wish", "don't wish", "Prefer not", "not want"] if answer_value == 'Decline' else [answer_value]
                    selected_opt = radio_options[0]
                    final_answer_display = option_labels_list[0]
                    for phrase in possible_phrases:
                        for idx, opt_label_str in enumerate(option_labels_list):
                            if phrase in opt_label_str:
                                selected_opt = radio_options[idx]
                                final_answer_display = f'Decline ({opt_label_str})' if len(possible_phrases) > 1 else opt_label_str
                                break
                        if selected_opt != radio_options[0]:
                            break
                    actions.move_to_element(selected_opt).click().perform()
                    if selected_opt == radio_options[0]:
                        randomly_filled_questions.add((f'{label_raw} ]', "radio"))
            else:
                answer_value = previous_answer
            questions_set.add((label_raw + " ]", answer_value, "radio", previous_answer))
            continue

        # Handle text inputs
        text_input_elem = try_xp(question_element, ".//input[@type='text']", False)
        if text_input_elem:
            need_actions = False
            label_elem = try_xp(question_element, ".//label[@for]", False)
            try:
                label_elem = label_elem.find_element(By.CLASS_NAME, 'visually-hidden')
            except:
                pass
            label_raw = label_elem.text if label_elem else "Unknown"
            answer_value = ""
            label_lower = label_raw.lower()
            previous_value = text_input_elem.get_attribute("value")

            if not previous_value or overwrite_previous_answers:
                if 'experience' in label_lower or 'years' in label_lower:
                    answer_value = years_of_experience
                elif 'phone' in label_lower or 'mobile' in label_lower:
                    answer_value = phone_number
                elif 'street' in label_lower:
                    answer_value = street
                elif 'city' in label_lower or 'location' in label_lower or 'address' in label_lower:
                    answer_value = current_city if current_city else job_location
                    need_actions = True
                elif 'signature' in label_lower:
                    answer_value = full_name
                elif 'name' in label_lower:
                    if 'full' in label_lower:
                        answer_value = full_name
                    elif 'first' in label_lower and 'last' not in label_lower:
                        answer_value = _first
                    elif 'middle' in label_lower and 'last' not in label_lower:
                        answer_value = _middle
                    elif 'last' in label_lower and 'first' not in label_lower:
                        answer_value = _last
                    elif 'employer' in label_lower:
                        answer_value = recent_employer
                    else:
                        answer_value = full_name
                elif 'notice' in label_lower:
                    if 'month' in label_lower:
                        answer_value = notice_period_in_months
                    elif 'week' in label_lower:
                        answer_value = notice_period_in_weeks
                    else:
                        answer_value = notice_period_str
                elif 'salary' in label_lower or 'compensation' in label_lower or 'ctc' in label_lower or 'pay' in label_lower:
                    if 'current' in label_lower or 'present' in label_lower:
                        if 'month' in label_lower:
                            answer_value = current_ctc_per_month
                        elif 'lakh' in label_lower:
                            answer_value = current_ctc_in_lakhs
                        else:
                            answer_value = current_ctc_str
                    else:
                        if 'month' in label_lower:
                            answer_value = desired_salary_per_month
                        elif 'lakh' in label_lower:
                            answer_value = desired_salary_in_lakhs
                        else:
                            answer_value = desired_salary_str
                elif 'linkedin' in label_lower:
                    answer_value = linkedIn
                elif any(x in label_lower for x in ['website', 'blog', 'portfolio', 'link']):
                    answer_value = website
                elif 'scale of 1-10' in label_lower:
                    answer_value = confidence_level
                elif 'headline' in label_lower:
                    answer_value = linkedin_headline
                elif ('hear' in label_lower or 'come across' in label_lower) and 'this' in label_lower and ('job' in label_lower or 'position' in label_lower):
                    answer_value = "https://github.com/GodsScion/Auto_job_applier_linkedIn"
                elif 'state' in label_lower or 'province' in label_lower:
                    answer_value = state
                elif 'zip' in label_lower or 'postal' in label_lower or 'code' in label_lower:
                    answer_value = zipcode
                elif 'country' in label_lower:
                    answer_value = country
                else:
                    answer_value = handle_common_question_response(label_lower, answer_value)

                if answer_value == "":
                    if use_AI and ai_client_instance:
                        try:
                            if ai_provider.lower() == "openai":
                                answer_value = ai_answer_question(ai_client_instance, label_raw, question_type="text", job_description=job_description, user_information_all=user_information_all)
                            elif ai_provider.lower() == "deepseek":
                                answer_value = deepseek_answer_question(ai_client_instance, label_raw, options=None, question_type="text", job_description=job_description, about_company=None, user_information_all=user_information_all)
                            elif ai_provider.lower() == "gemini":
                                answer_value = gemini_answer_question(ai_client_instance, label_raw, options=None, question_type="text", job_description=job_description, about_company=None, user_information_all=user_information_all)
                            else:
                                randomly_filled_questions.add((label_raw, "text"))
                                answer_value = years_of_experience
                            if answer_value and isinstance(answer_value, str) and len(answer_value) > 0:
                                print_lg(f'AI answered "{label_raw}" with: "{answer_value}"')
                            else:
                                randomly_filled_questions.add((label_raw, "text"))
                                answer_value = years_of_experience
                        except Exception as e:
                            print_lg("AI answer failed, using fallback.", e)
                            randomly_filled_questions.add((label_raw, "text"))
                            answer_value = years_of_experience
                    else:
                        randomly_filled_questions.add((label_raw, "text"))
                        answer_value = years_of_experience

                text_input_elem.clear()
                text_input_elem.send_keys(answer_value)
                if need_actions:
                    sleep(2)
                    actions.send_keys(Keys.ARROW_DOWN)
                    actions.send_keys(Keys.ENTER).perform()
            questions_set.add((label_lower, text_input_elem.get_attribute("value"), "text", previous_value))
            continue

        # Handle textareas
        textarea_elem = try_xp(question_element, ".//textarea", False)
        if textarea_elem:
            label_elem = try_xp(question_element, ".//label[@for]", False)
            label_raw = label_elem.text if label_elem else "Unknown"
            label_lower = label_raw.lower()
            answer_value = ""
            previous_value = textarea_elem.get_attribute("value")

            if not previous_value or overwrite_previous_answers:
                if 'summary' in label_lower:
                    answer_value = linkedin_summary
                elif 'cover' in label_lower:
                    answer_value = cover_letter

                if answer_value == "":
                    if use_AI and ai_client_instance:
                        try:
                            if ai_provider.lower() == "openai":
                                answer_value = ai_answer_question(ai_client_instance, label_raw, question_type="textarea", job_description=job_description, user_information_all=user_information_all)
                            elif ai_provider.lower() == "deepseek":
                                answer_value = deepseek_answer_question(ai_client_instance, label_raw, options=None, question_type="textarea", job_description=job_description, about_company=None, user_information_all=user_information_all)
                            elif ai_provider.lower() == "gemini":
                                answer_value = gemini_answer_question(ai_client_instance, label_raw, options=None, question_type="textarea", job_description=job_description, about_company=None, user_information_all=user_information_all)
                            else:
                                randomly_filled_questions.add((label_raw, "textarea"))
                                answer_value = ""
                            if answer_value and isinstance(answer_value, str) and len(answer_value) > 0:
                                print_lg(f'AI answered "{label_raw}" with: "{answer_value}"')
                            else:
                                randomly_filled_questions.add((label_raw, "textarea"))
                                answer_value = ""
                        except Exception as e:
                            print_lg("AI answer failed.", e)
                            randomly_filled_questions.add((label_raw, "textarea"))
                            answer_value = ""
                    else:
                        randomly_filled_questions.add((label_raw, "textarea"))
                        answer_value = ""

            textarea_elem.clear()
            textarea_elem.send_keys(answer_value)
            questions_set.add((label_lower, textarea_elem.get_attribute("value"), "textarea", previous_value))
            continue

        # Handle checkboxes
        checkbox_elem = try_xp(question_element, ".//input[@type='checkbox']", False)
        if checkbox_elem:
            label_elem = try_xp(question_element, ".//span[@class='visually-hidden']", False)
            label_raw = label_elem.text if label_elem else "Unknown"
            label_lower = label_raw.lower()
            answer_label = try_xp(question_element, ".//label[@for]", False)
            answer_text = answer_label.text if answer_label else "Unknown"
            previously_checked = checkbox_elem.is_selected()
            is_checked_now = previously_checked
            if not previously_checked:
                try:
                    actions.move_to_element(checkbox_elem).click().perform()
                    is_checked_now = True
                except Exception as e:
                    print_lg("Checkbox click failed.", e)
            questions_set.add((f'{label_lower} ([X] {answer_text})', is_checked_now, "checkbox", previously_checked))
            continue

    # Dismiss any date picker that might be open
    try_xp(driver, "//button[contains(@aria-label, 'This is today')]")
    return questions_set


def process_external_application(pagination_element: WebElement, job_id: str, job_url: str, resume_name: str, posted_date, external_link: str, screenshot_filename: str) -> tuple[bool, str, int]:
    """Handle jobs that require external application."""
    global tabs_open_count, daily_easy_apply_cap_reached

    if easy_apply_only:
        try:
            if "exceeded the daily application limit" in driver.find_element(By.CLASS_NAME, "artdeco-inline-feedback__message").text:
                daily_easy_apply_cap_reached = True
        except:
            pass
        print_lg("Easy Apply failed, but only Easy Apply jobs allowed.")
        if pagination_element is not None:
            return True, external_link, tabs_open_count

    try:
        wait.until(EC.element_to_be_clickable((By.XPATH, ".//button[contains(@class,'jobs-apply-button') and contains(@class, 'artdeco-button--3')]"))).click()
        wait_span_click(driver, "Continue", 1, True, False)
        all_windows = driver.window_handles
        tabs_open_count = len(all_windows)
        driver.switch_to.window(all_windows[-1])
        external_link = driver.current_url
        print_lg(f'External application link captured: "{external_link}"')
        if close_tabs and driver.current_window_handle != linkedIn_main_tab:
            driver.close()
        driver.switch_to.window(linkedIn_main_tab)
        return False, external_link, tabs_open_count
    except Exception as e:
        print_lg("Failed to handle external apply.")
        log_failed_application(job_id, job_url, resume_name, posted_date, "External apply failed", e, external_link, screenshot_filename)
        global failed_application_count
        failed_application_count += 1
        return True, external_link, tabs_open_count


def toggle_follow_company_checkbox(modal: WebDriver = driver) -> None:
    """Set the 'Follow Company' checkbox according to configuration."""
    try:
        checkbox = try_xp(modal, ".//input[@id='follow-company-checkbox' and @type='checkbox']", False)
        if checkbox and checkbox.is_selected() != follow_companies:
            try_xp(modal, ".//label[@for='follow-company-checkbox']")
    except Exception as e:
        print_lg("Failed to update follow company checkbox.", e)


def log_failed_application(job_id: str, job_url: str, resume_used: str, posted_date, error_msg: str, exception_obj: Exception, external_link: str, screenshot_name: str) -> None:
    """Write failed job details to CSV."""
    try:
        with open(failed_file_name, 'a', newline='', encoding='utf-8') as f:
            fieldnames = ['Job ID', 'Job Link', 'Resume Tried', 'Date listed', 'Date Tried', 'Assumed Reason', 'Stack Trace', 'External Job link', 'Screenshot Name']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow({
                'Job ID': truncate_for_csv(job_id),
                'Job Link': truncate_for_csv(job_url),
                'Resume Tried': truncate_for_csv(resume_used),
                'Date listed': truncate_for_csv(posted_date),
                'Date Tried': datetime.now(),
                'Assumed Reason': truncate_for_csv(error_msg),
                'Stack Trace': truncate_for_csv(exception_obj),
                'External Job link': truncate_for_csv(external_link),
                'Screenshot Name': truncate_for_csv(screenshot_name)
            })
    except Exception as e:
        print_lg("Failed to update failed jobs log!", e)
        pyautogui.alert("Could not write to failed jobs CSV.", "Logging Error")


def capture_screenshot(webdriver_instance: WebDriver, job_id: str, failure_point: str) -> str:
    """Take a screenshot and return filename."""
    filename = f"{job_id} - {failure_point} - {str(datetime.now())}.png".replace(":", ".")
    path = os.path.join(logs_folder_path, "screenshots", filename)
    webdriver_instance.save_screenshot(path)
    return filename


def record_successful_application(
    job_id: str, title: str, company: str, work_location: str, work_style: str,
    description: str, required_exp: int | Literal['Unknown', 'Error in extraction'],
    skills: list[str] | Literal['In Development'], hr_name: str | Literal['Unknown'],
    hr_link: str | Literal['Unknown'], resume_used: str, reposted: bool,
    date_posted: datetime | Literal['Unknown'], date_applied: datetime | Literal['Pending'],
    job_url: str, external_link: str, questions_answered: set | None,
    connect_req: Literal['In Development']
) -> None:
    """Log successfully applied job to CSV."""
    try:
        with open(file_name, mode='a', newline='', encoding='utf-8') as f:
            fieldnames = [
                'Job ID', 'Title', 'Company', 'Work Location', 'Work Style',
                'About Job', 'Experience required', 'Skills required', 'HR Name',
                'HR Link', 'Resume', 'Re-posted', 'Date Posted', 'Date Applied',
                'Job Link', 'External Job link', 'Questions Found', 'Connect Request'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow({
                'Job ID': truncate_for_csv(job_id),
                'Title': truncate_for_csv(title),
                'Company': truncate_for_csv(company),
                'Work Location': truncate_for_csv(work_location),
                'Work Style': truncate_for_csv(work_style),
                'About Job': truncate_for_csv(description),
                'Experience required': truncate_for_csv(required_exp),
                'Skills required': truncate_for_csv(skills),
                'HR Name': truncate_for_csv(hr_name),
                'HR Link': truncate_for_csv(hr_link),
                'Resume': truncate_for_csv(resume_used),
                'Re-posted': truncate_for_csv(reposted),
                'Date Posted': truncate_for_csv(date_posted),
                'Date Applied': truncate_for_csv(date_applied),
                'Job Link': truncate_for_csv(job_url),
                'External Job link': truncate_for_csv(external_link),
                'Questions Found': truncate_for_csv(questions_answered),
                'Connect Request': truncate_for_csv(connect_req)
            })
    except Exception as e:
        print_lg("Failed to log successful application!", e)
        pyautogui.alert("Could not write to applied jobs CSV.", "Logging Error")


def discard_job_modal() -> None:
    """Close the Easy Apply modal without saving."""
    actions.send_keys(Keys.ESCAPE).perform()
    wait_span_click(driver, 'Discard', 2)


def apply_to_jobs_for_search_term(search_terms: list[str]) -> None:
    """Main loop that iterates over search terms and applies to jobs."""
    applied_job_ids = fetch_previously_applied_job_ids()
    rejected_job_ids = set()
    blacklisted_company_names = set()

    global current_city, failed_application_count, skipped_job_count, successful_easy_applies
    global external_link_collected_count, tabs_open_count, pause_before_submit, pause_at_failed_question, use_new_resume_flag

    current_city = current_city.strip()

    if randomize_search_order:
        shuffle(search_terms)

    for term in search_terms:
        driver.get(f"https://www.linkedin.com/jobs/search/?keywords={term}")
        print_lg("\n" + "_" * 120 + "\n")
        print_lg(f'\n>>>> Searching for: "{term}" <<<<\n')

        apply_all_search_filters()

        current_job_counter = 0
        try:
            while current_job_counter < switch_number:
                wait.until(EC.presence_of_all_elements_located((By.XPATH, "//li[@data-occludable-job-id]")))
                pagination, current_page_num = retrieve_pagination_info()
                buffer(3)
                job_cards = driver.find_elements(By.XPATH, "//li[@data-occludable-job-id]")

                for job_card in job_cards:
                    if keep_screen_awake:
                        pyautogui.press('shiftright')
                    if current_job_counter >= switch_number:
                        break
                    print_lg("\n-@-\n")

                    job_id, job_title, company_name, location_clean, work_type, skip_job = extract_job_card_details(
                        job_card, blacklisted_company_names, rejected_job_ids
                    )

                    if skip_job:
                        continue

                    try:
                        if job_id in applied_job_ids or find_by_class(driver, "jobs-s-apply__application-link", 2):
                            print_lg(f'Already applied: "{job_title} | {company_name}" (ID: {job_id})')
                            continue
                    except:
                        print_lg(f'Attempting to apply: "{job_title} | {company_name}" (ID: {job_id})')

                    job_url = "https://www.linkedin.com/jobs/view/" + job_id
                    external_application_url = "Easy Applied"
                    date_applied = "Pending"
                    hr_profile_link = "Unknown"
                    hr_name = "Unknown"
                    connect_request_status = "In Development"
                    posting_date = "Unknown"
                    extracted_skills = "Needs an AI"
                    resume_filename = "Pending"
                    is_reposted = False
                    answered_questions_set = None
                    screenshot_file = "Not Available"

                    try:
                        rejected_job_ids, blacklisted_company_names, top_card = screen_company_description(
                            rejected_job_ids, job_id, company_name, blacklisted_company_names
                        )
                    except ValueError as err:
                        print_lg(err, 'Skipping job due to blacklist.')
                        log_failed_application(job_id, job_url, resume_filename, posting_date, "Blacklisted company content", err, "Skipped", screenshot_file)
                        skipped_job_count += 1
                        continue
                    except Exception as err:
                        print_lg("Error while checking company description.")

                    try:
                        hr_info = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.CLASS_NAME, "hirer-card__hirer-information")))
                        hr_profile_link = hr_info.find_element(By.TAG_NAME, "a").get_attribute("href")
                        hr_name = hr_info.find_element(By.TAG_NAME, "span").text
                    except:
                        print_lg(f'No HR info for "{job_title}" (ID: {job_id})')

                    try:
                        time_posted_str = top_card.find_element(By.XPATH, './/span[contains(normalize-space(), " ago")]').text
                        print("Time Posted: " + time_posted_str)
                        if "Reposted" in time_posted_str:
                            is_reposted = True
                            time_posted_str = time_posted_str.replace("Reposted", "")
                        posting_date = calculate_date_posted(time_posted_str.strip())
                    except Exception as e:
                        print_lg("Failed to parse posted date.", e)

                    job_desc, required_exp_years, should_skip, skip_reason, skip_msg = extract_job_description_details()
                    if should_skip:
                        print_lg(skip_msg)
                        log_failed_application(job_id, job_url, resume_filename, posting_date, skip_reason, skip_msg, "Skipped", screenshot_file)
                        rejected_job_ids.add(job_id)
                        skipped_job_count += 1
                        continue

                    if use_AI and job_desc != "Unknown":
                        try:
                            if ai_provider.lower() == "openai":
                                extracted_skills = ai_extract_skills(ai_client_instance, job_desc)
                            elif ai_provider.lower() == "deepseek":
                                extracted_skills = deepseek_extract_skills(ai_client_instance, job_desc)
                            elif ai_provider.lower() == "gemini":
                                extracted_skills = gemini_extract_skills(ai_client_instance, job_desc)
                            else:
                                extracted_skills = "In Development"
                            print_lg(f"Skills extracted via {ai_provider} AI.")
                        except Exception as e:
                            print_lg("Skill extraction failed:", e)
                            extracted_skills = "Error extracting skills"

                    resume_uploaded = False
                    if try_xp(driver, ".//button[contains(@class,'jobs-apply-button') and contains(@class, 'artdeco-button--3') and contains(@aria-label, 'Easy')]"):
                        try:
                            modal_container = find_by_class(driver, "jobs-easy-apply-modal")
                            wait_span_click(modal_container, "Next", 1)
                            resume_filename = "Previous resume"
                            next_button_present = True
                            answered_questions_set = set()
                            next_button_press_count = 0

                            while next_button_present:
                                next_button_press_count += 1
                                if next_button_press_count >= 15:
                                    if pause_at_failed_question:
                                        capture_screenshot(driver, job_id, "Needed manual intervention for failed question")
                                        pyautogui.alert(
                                            "Couldn't answer one or more questions.\nPlease click \"Continue\" once done.\nDO NOT CLICK Back, Next or Review button.",
                                            "Help Needed", "Continue"
                                        )
                                        next_button_press_count = 1
                                        continue
                                    if answered_questions_set:
                                        print_lg("Stuck on questions:", answered_questions_set)
                                    screenshot_file = capture_screenshot(driver, job_id, "Failed at questions")
                                    raise Exception("Infinite loop detected during question answering.")

                                answered_questions_set = fill_application_questions(
                                    modal_container, answered_questions_set, location_clean, job_description=job_desc
                                )
                                if use_new_resume_flag and not resume_uploaded:
                                    resume_uploaded, resume_filename = upload_resume_file(modal_container, default_resume_path)

                                try:
                                    next_button_present = modal_container.find_element(By.XPATH, './/span[normalize-space(.)="Review"]')
                                except NoSuchElementException:
                                    next_button_present = modal_container.find_element(By.XPATH, './/button[contains(span, "Next")]')
                                try:
                                    next_button_present.click()
                                except ElementClickInterceptedException:
                                    break
                                buffer(click_gap)

                        except NoSuchElementException:
                            pass
                        finally:
                            if answered_questions_set:
                                print_lg("Answered questions:", answered_questions_set)
                            wait_span_click(driver, "Review", 1, scrollTop=True)
                            original_pause_setting = pause_before_submit
                            if original_pause_setting:
                                user_decision = pyautogui.confirm(
                                    '1. Please verify your information.\n2. DO NOT CLICK "Submit Application".',
                                    "Confirm Details",
                                    ["Disable Pause", "Discard Application", "Submit Application"]
                                )
                                if user_decision == "Discard Application":
                                    raise Exception("User discarded application.")
                                pause_before_submit = False if user_decision == "Disable Pause" else True

                            toggle_follow_company_checkbox(modal_container)

                            if wait_span_click(driver, "Submit application", 2, scrollTop=True):
                                date_applied = datetime.now()
                                if not wait_span_click(driver, "Done", 2):
                                    actions.send_keys(Keys.ESCAPE).perform()
                            elif original_pause_setting and "Yes" in pyautogui.confirm("Did you manually submit?", "Submit Confirmation", ["Yes", "No"]):
                                date_applied = datetime.now()
                                wait_span_click(driver, "Done", 2)
                            else:
                                print_lg("Submit button not found. Discarding.")
                                raise Exception("Failed to click Submit application.")

                    else:
                        should_skip_external, external_application_url, tabs_open_count = process_external_application(
                            pagination, job_id, job_url, resume_filename, posting_date, external_application_url, screenshot_file
                        )
                        if daily_easy_apply_cap_reached:
                            print_lg("\n####### Daily Easy Apply limit reached. #######\n")
                            return
                        if should_skip_external:
                            continue

                    record_successful_application(
                        job_id, job_title, company_name, location_clean, work_type,
                        job_desc, required_exp_years, extracted_skills, hr_name,
                        hr_profile_link, resume_filename, is_reposted, posting_date,
                        date_applied, job_url, external_application_url,
                        answered_questions_set, connect_request_status
                    )
                    if resume_uploaded:
                        use_new_resume_flag = False

                    print_lg(f'Successfully processed "{job_title} | {company_name}" (ID: {job_id})')
                    current_job_counter += 1
                    if external_application_url == "Easy Applied":
                        successful_easy_applies += 1
                    else:
                        external_link_collected_count += 1
                    applied_job_ids.add(job_id)

                if pagination is None:
                    print_lg("No pagination found; likely at last page.")
                    break
                try:
                    pagination.find_element(By.XPATH, f"//button[@aria-label='Page {current_page_num + 1}']").click()
                    print_lg(f"\n>-> Moving to Page {current_page_num + 1}\n")
                except NoSuchElementException:
                    print_lg(f"\n>-> Page {current_page_num + 1} not found; end of results.\n")
                    break

        except (NoSuchWindowException, WebDriverException) as e:
            print_lg("Browser closed or session invalid.", e)
            raise e
        except Exception as e:
            print_lg("Error during job listing processing.")
            critical_error_log("In Applier", e)


def execute_application_cycle(total_cycles: int) -> int:
    """Perform one full application cycle."""
    if daily_easy_apply_cap_reached:
        return total_cycles
    print_lg("\n" + "#" * 120 + "\n")
    print_lg(f"Date and Time: {datetime.now()}")
    print_lg(f"Cycle number: {total_cycles}")
    print_lg(f"Filter: date_posted='{date_posted}', sort_by='{sort_by}'")
    apply_to_jobs_for_search_term(search_terms)
    print_lg("#" * 120 + "\n")
    if not daily_easy_apply_cap_reached:
        print_lg("Sleeping for 10 minutes...")
        sleep(300)
        print_lg("Resuming shortly...")
        sleep(300)
    buffer(3)
    return total_cycles + 1


# Global window handles
chatGPT_tab = False
linkedIn_main_tab = False


def main() -> None:
    """Entry point of the script."""
    try:
        global linkedIn_main_tab, tabs_open_count, use_new_resume_flag, ai_client_instance
        alert_title = "Error Occurred. Closing Browser!"
        cycles_completed = 1

        validate_config()

        if not os.path.exists(default_resume_path):
            pyautogui.alert(
                text=f'Resume file "{default_resume_path}" not found! Update "default_resume_path" in config.py.\n\nBot will use previously uploaded resume.',
                title="Missing Resume", button="OK"
            )
            use_new_resume_flag = False

        tabs_open_count = len(driver.window_handles)
        driver.get("https://www.linkedin.com/login")
        if not verify_logged_in_linkedin():
            perform_linkedin_login()

        linkedIn_main_tab = driver.current_window_handle

        if use_AI:
            if ai_provider == "openai":
                ai_client_instance = ai_create_openai_client()
            elif ai_provider == "deepseek":
                ai_client_instance = deepseek_create_client()
            elif ai_provider == "gemini":
                ai_client_instance = gemini_create_client()

        driver.switch_to.window(linkedIn_main_tab)
        cycles_completed = execute_application_cycle(cycles_completed)

        while run_non_stop:
            if cycle_date_posted:
                date_options_list = ["Any time", "Past month", "Past week", "Past 24 hours"]
                global date_posted
                idx = date_options_list.index(date_posted)
                next_idx = idx + 1 if idx + 1 < len(date_options_list) else (0 if stop_date_cycle_at_24hr else -1)
                date_posted = date_options_list[next_idx]
            if alternate_sortby:
                global sort_by
                sort_by = "Most recent" if sort_by == "Most relevant" else "Most relevant"
                cycles_completed = execute_application_cycle(cycles_completed)
                sort_by = "Most recent" if sort_by == "Most relevant" else "Most relevant"
            cycles_completed = execute_application_cycle(cycles_completed)
            if daily_easy_apply_cap_reached:
                break

    except (NoSuchWindowException, WebDriverException) as e:
        print_lg("Browser closed unexpectedly.", e)
    except Exception as e:
        critical_error_log("In Applier Main", e)
        pyautogui.alert(e, alert_title)
    finally:
        print_lg(f"\n\nTotal cycles:                     {cycles_completed}")
        print_lg(f"Jobs Easy Applied:                {successful_easy_applies}")
        print_lg(f"External job links collected:     {external_link_collected_count}")
        print_lg(f"                              ----------")
        print_lg(f"Total applied or collected:       {successful_easy_applies + external_link_collected_count}")
        print_lg(f"\nFailed jobs:                      {failed_application_count}")
        print_lg(f"Irrelevant jobs skipped:          {skipped_job_count}\n")
        if randomly_filled_questions:
            print_lg("\n\nRandomly answered questions:\n  " + ";\n".join(str(q) for q in randomly_filled_questions) + "\n\n")

        farewell_quote = choice([
            "You're one step closer than before.",
            "All the best with your future interviews.",
            "Keep up with the progress. You got this.",
            "If you're tired, learn to take rest but never give up.",
            "Success is not final, failure is not fatal: It is the courage to continue that counts. - Winston Churchill",
            "Believe in yourself and all that you are. Know that there is something inside you that is greater than any obstacle. - Christian D. Larson",
            "Every job is a self-portrait of the person who does it. Autograph your work with excellence.",
            "The only way to do great work is to love what you do. If you haven't found it yet, keep looking. Don't settle. - Steve Jobs",
            "Opportunities don't happen, you create them. - Chris Grosser",
            "The road to success and the road to failure are almost exactly the same. The difference is perseverance.",
            "Obstacles are those frightful things you see when you take your eyes off your goal. - Henry Ford",
            "The only limit to our realization of tomorrow will be our doubts of today. - Franklin D. Roosevelt"
        ])
        final_message = f"\n{farewell_quote}\n\n\nBest regards,\nPrem Kumar & Vala Chintan \nhttps://www.linkedin.com/in/prem-kumar007/\n\n"
        pyautogui.alert(final_message, "Exiting..")
        print_lg(final_message, "Closing browser...")
        if tabs_open_count >= 10:
            warning_msg = "NOTE: IF YOU HAVE MORE THAN 10 TABS OPENED, PLEASE CLOSE OR BOOKMARK THEM!\n\nOr it's highly likely that application will just open browser and not do anything next time!"
            pyautogui.alert(warning_msg, "Info")
            print_lg("\n" + warning_msg)

        if use_AI and ai_client_instance:
            try:
                if ai_provider.lower() == "openai":
                    ai_close_openai_client(ai_client_instance)
                elif ai_provider.lower() == "deepseek":
                    ai_close_openai_client(ai_client_instance)
                elif ai_provider.lower() == "gemini":
                    pass
                print_lg(f"Closed {ai_provider} AI client.")
            except Exception as e:
                print_lg("Failed to close AI client:", e)

        try:
            if driver:
                driver.quit()
        except WebDriverException:
            print_lg("Browser already closed.")
        except Exception as e:
            critical_error_log("When quitting...", e)


if __name__ == "__main__":
    main()
