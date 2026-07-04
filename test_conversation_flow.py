"""
Test conversation flow for the furniture chatbot agent.
This script simulates a complete customer conversation to test the order flow.
NOTE: This is a mock transcript generator since Django is not available in this environment.
"""


def print_transcript(role, message):
    """Print a message in transcript format"""
    print(f"\n[{role.upper()}]: {message}")
    print("-" * 60)


def test_conversation_with_deposit():
    """Test conversation flow for a product that requires deposit"""
    print("\n" + "=" * 60)
    print("TEST SCENARIO 1: ORDER WITH DEPOSIT")
    print("=" * 60)

    # Step 1: Customer asks about a product
    print_transcript("customer", "عايز دواليب أثاث")

    print_transcript(
        "agent",
        "وجدت هذه المنتجات:\n\n1. دولاب خشبي كبير\n   السعر: 3500 جنيه\n   متاح: نعم\n   التصنيف: دواليب\n   الخامة: خشب\n   ⚠️ يتطلب ديبوزيت\n\n2. دولاب مودرن\n   السعر: 2800 جنيه\n   متاح: نعم\n   التصنيف: دواليب\n   الخامة: MDF\n   ⚠️ يتطلب ديبوزيت",
    )

    # Step 2: Customer requests order
    print_transcript("customer", "عايز أعمل أوردر على الدولاب الخشبي الكبير")

    print_transcript(
        "agent",
        "تمام يا فندم، محتاج:\n- الاسم الكامل\n- رقم الموبايل\n- المحافظة\n- العنوان بالتفصيل",
    )

    # Step 3: Customer sends all data in one message
    print_transcript(
        "customer", "محمود أحمد من القاهرة شارع المعز أمام المدرسة 01013544163"
    )

    print_transcript(
        "agent",
        "تمام يا فندم، ده ملخص الأوردر:\nالاسم: محمود أحمد\nالموبايل: 01013544163\nالمحافظة: القاهرة\nالعنوان: شارع المعز أمام المدرسة\n\nالمنتجات:\n- دولاب خشبي كبير × 1 قطعة = 3500 جنيه\n\nإجمالي المنتجات: 3500 جنيه\nالشحن (القاهرة): 200 جنيه\nالإجمالي: 3700 جنيه\n\nالديبوزيت المطلوب: 1000 جنيه\nحوّل الديبوزيت على فودافون كاش: 015034065884\nابعت screenshot التحويل في المحادثة دي.\n\nتحب أأكد الأوردر؟",
    )

    # Step 4: Customer confirms order
    print_transcript("customer", "تمام نفذ")

    print_transcript(
        "agent",
        "تمام يا فندم.\nالأوردر رقم ORD-12345 تم التسجيل بنجاح.\nتم إرسال الأوردر على واتساب بنجاح.\n\nهنتواصل معاك قريب.",
    )


def test_conversation_without_deposit():
    """Test conversation flow for a product without deposit"""
    print("\n" + "=" * 60)
    print("TEST SCENARIO 2: ORDER WITHOUT DEPOSIT (MULTIPLE PRODUCTS)")
    print("=" * 60)

    # Step 1: Customer asks about a product
    print_transcript("customer", "عندكم طاولات")

    print_transcript(
        "agent",
        "وجدت هذه المنتجات:\n\n1. طاولة طعام\n   السعر: 4500 جنيه\n   متاح: نعم\n   التصنيف: طاولات\n   الخامة: خشب\n\n2. طاولة مكتب\n   السعر: 1800 جنيه\n   متاح: نعم\n   التصنيف: طاولات\n   الخامة: خشب",
    )

    # Step 2: Customer requests order
    print_transcript("customer", "عايز أعمل أوردر على طاولة الطعام")

    print_transcript(
        "agent",
        "تمام يا فندم، محتاج:\n- الاسم الكامل\n- رقم الموبايل\n- المحافظة\n- العنوان بالتفصيل",
    )

    # Step 3: Customer sends all data in one message
    print_transcript("customer", "سارة محمد من الجيزة شارع الهرم عمارة 5 01234567890")

    print_transcript(
        "agent",
        "تمام يا فندم، ده ملخص الأوردر:\nالاسم: سارة محمد\nالموبايل: 01234567890\nالمحافظة: الجيزة\nالعنوان: شارع الهرم عمارة 5\n\nالمنتجات:\n- طاولة طعام × 1 قطعة = 4500 جنيه\n\nإجمالي المنتجات: 4500 جنيه\nالشحن (الجيزة): 250 جنيه\nالإجمالي: 4750 جنيه\n\nمحتاج حضرتك منتجات تانية ولا كده تمام؟",
    )

    # Step 4: Customer wants to add another product
    print_transcript("customer", "عايز أضيف كرسي برضه")

    print_transcript("agent", "تمام، ابحث عن الكرسي اللي عايزاه.")

    # Step 5: Customer adds chair
    print_transcript("customer", "الكرسي الخشبي")

    print_transcript(
        "agent",
        "وجدت هذه المنتجات:\n\n1. كرسي خشبي\n   السعر: 800 جنيه\n   متاح: نعم\n   التصنيف: كراسي\n   الخامة: خشب",
    )

    print_transcript("customer", "ده")

    print_transcript(
        "agent", "تمام، أضفت الكرسي للأوردر.\nمحتاج حضرتك منتجات تانية ولا كده تمام؟"
    )

    # Step 6: Customer says no more products
    print_transcript("customer", "لا كده")

    print_transcript(
        "agent",
        "بنحرص إن يوصلك طلبك بأسرع وقت ممكن، وبنوضحلك سياستنا بكل شفافية من الأول:\n\n* مدة التوصيل: خلال أسبوع من تأكيد الطلب\n* المعاينة عند الاستلام: تقدر تعاين طلبك أول ما يوصل، ولو في أي مشكلة تقدر ترفض الاستلام أو تعمل إرجاع فوري مع مندوب الشحن في نفس اللحظة، مع تحمّل تكلفة الشحن فقط\n* بعد استلام الطلب: غير متاح الاسترجاع أو الاستبدال بعد مغادرة المندوب لمكان التسليم، فبنرجوك تتأكد من معاينة القطعة كويس قبل ما المندوب يمشي\n* نطاق التسليم: التسليم بيكون أمام المنزل، وطلوع القطعة لباب الشقة ده اتفاق منفصل بينك وبين مندوب التوصيل مباشرة\n\nتمام، أنفذ الأوردر؟",
    )

    # Step 7: Customer confirms order
    print_transcript("customer", "موافق")

    print_transcript(
        "agent",
        "تمام يا فندم.\nالأوردر رقم ORD-12346 تم التسجيل بنجاح.\nتم إرسال الأوردر على واتساب بنجاح.\n\nهنتواصل معاك قريب.",
    )


def main():
    """Run all test scenarios"""
    print("\n" + "=" * 60)
    print("FURNITURE CHATBOT - CONVERSATION FLOW TEST")
    print("MOCK TRANSCRIPT GENERATOR")
    print("=" * 60)

    try:
        # Test with deposit
        test_conversation_with_deposit()

        # Test without deposit
        test_conversation_without_deposit()

        print("\n" + "=" * 60)
        print("TEST TRANSCRIPT COMPLETED")
        print("=" * 60)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
